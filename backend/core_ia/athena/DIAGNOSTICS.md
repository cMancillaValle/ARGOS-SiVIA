# Diagnóstico de Rendimiento y Telemetría de Athena

Documentación técnica de la instrumentación diagnóstica implementada en ARGOS-SiVIA v1.7.5 para el motor de visión artificial Athena.

---

## 1. Consulta y Control de Acceso (RBAC)

- **Endpoint**: `GET /api/camaras/athena/diagnostics`
- **Filtro opcional**: `?cam_id=<id>` (restringe la consulta a las sesiones de una cámara específica).
- **Autenticación**: Requiere token de sesión activo mediante header `X-Token` o cookie autorizada.
- **Permisos requeridos (RBAC)**: Requiere al menos uno de los permisos `camaras:ver` o `camaras:ver_detalle`. Usuarios sin permisos de visualización reciben respuesta `403 Forbidden`.
- **Validación de entidad**: Si se proporciona `cam_id`, el endpoint verifica la existencia de la cámara en la base de datos; si no existe, devuelve `404 Not Found`.
- **Privacidad y seguridad**: La respuesta **no expone** URLs RTSP, direcciones IP, nombres de usuario, contraseñas ni rutas locales de archivos fuente. Las sesiones se identifican mediante identificadores únicos opacos (`session_id`).

---

## 2. Ciclo de Vida de las Sesiones

Cada inicio de cámara a través de Athena genera una sesión diagnóstica aislada en memoria vinculada al ciclo de vida de su hilo gestor `AthenaThread`:

- **Sesión activa (`is_active: true`)**:
  - Describe el estado del hilo gestor `AthenaThread`, que permanece activo controlando la cámara.
  - **Reinicio del subproceso worker**: `is_active: true` **no garantiza que el subproceso `athena_worker.py` esté en ejecución en todo momento**. Si el worker termina de forma inesperada (p. ej. caída transitoria de la fuente de video, error de decodificación o señal de reinicio), el bucle de `AthenaThread.run()` limpia el proceso terminado y lanza un nuevo subproceso worker automáticamente. Durante este reintento, **la sesión diagnóstica continúa activa** y no se cierra ni reinicia.
  - **Tiempo de espera en detención**: Si se solicita detener o reiniciar una cámara y el hilo `AthenaThread` no logra finalizar dentro del tiempo límite de espera (`join(timeout=5)`), la sesión diagnóstica **permanece activa** (`is_active: true`) para no falsear el estado mientras el hilo siga en ejecución.
  - La duración transcurrida (`elapsed_s`) es dinámica y se calcula en tiempo real al momento de la consulta (`time.perf_counter() - started_at`).
- **Sesión finalizada (`is_active: false`)**:
  - Una sesión diagnóstica finaliza **cuando `AthenaThread` termina de forma definitiva o si no pudo iniciar**:
    1. **Detención manual o reinicio exitoso**: Al invocar `AthenaManager.stop(cam_id)` o al reiniciar la cámara mediante `AthenaManager.start(cam_id)`, una vez que el hilo ha finalizado efectivamente.
    2. **Fallo de inicio del hilo**: Si `worker.start()` lanza una excepción en el sistema operativo, las referencias se limpian y la sesión se archiva inmediatamente como finalizada.
    3. **Fallo de entorno virtual**: Si `_check_venv()` detecta que el intérprete de Python o el entorno virtual no están disponibles.
    4. **Excepción no controlada**: Cualquier error crítico no atrapado que fuerce la salida del hilo.
    5. **Salida normal**: Tras completarse el bucle principal ante la señal de parada (`_stop_ev`).
  - **Archivado idempotente**: La finalización de la sesión se ejecuta de manera idempotente coordinada entre `AthenaThread` y `AthenaManager`:
    - Se archiva una única vez evitando duplicaciones.
    - Se verifica que el `session_id` coincida con la sesión activa de la cámara para impedir que la terminación tardía de un hilo anterior sobrescriba una sesión nueva recién iniciada.
    - Se registran `ended_at` (marca de tiempo Unix), `duration_s` y `elapsed_s` con la duración total real congelada al cierre, y se establece `is_active: false`.
- **Retención en memoria**:
  - El backend mantiene en memoria todas las sesiones activas y un historial de **hasta 20 sesiones finalizadas** (ordenadas por `ended_at` bajo política FIFO).
  - Toda la telemetría reside exclusivamente en memoria volátil; un reinicio del backend restablece este historial.

---

## 3. Contadores (`counts`) y Secuencia

Los contadores reflejan el comportamiento exacto del flujo de captura y procesamiento:

- **`captured`**: Número total de llamadas exitosas a `VideoCapture.read()` ejecutadas por el hilo productor de captura (`FastCameraReader`) desde el inicio de la sesión.
- **`capture_read_failures`**: Número de llamadas a `VideoCapture.read()` que devolvieron `ret == False` (fallos transitorios de lectura o desconexión temporal de la fuente).
- **`processed`**: Número de iteraciones del ciclo principal del worker que completaron el procesamiento y alcanzaron el punto previo a la codificación JPEG. No garantiza que la compresión `cv2.imencode()` haya tenido éxito.
- **`transmitted`**: Contabiliza los fotogramas JPEG correspondientes a frames procesados que fueron enviados por el pipe hacia el backend. Los fotogramas de placeholder ("SIN SEÑAL") también pueden enviarse como mensajes de imagen, pero no incrementan este contador.
- **`consumer_repeats`**: Veces que el hilo consumidor principal (`main`) recibió consecutivamente el mismo identificador de secuencia de fotograma (`frame_sequence == last_consumed_sequence`). Ocurre cuando el ciclo de procesamiento procesa más rápido de lo que la cámara produce nuevos fotogramas. Esta métrica permite dimensionar sobreprocesamiento sin descartar fotogramas ni alterar la lógica de negocio.
- **`latest_capture_sequence`**: Identificador entero monotónico incremental asignado a cada fotograma capturado por el hilo productor. Permite auditar la sincronía productor-consumidor de forma segura.

---

## 4. Tasas de Fotogramas por Ventana (`fps` y `window_s`)

- **`window_s`**: Duración en segundos transcurrida desde la emisión del reporte anterior (aproximadamente 5.0 segundos).
- **`fps.captured`**: Tasa media de captura por segundo durante la ventana reciente (`captured_en_ventana / window_s`).
- **`fps.processed`**: Tasa media de fotogramas procesados por segundo durante la ventana reciente (`processed_en_ventana / window_s`).
- **`fps.transmitted`**: Tasa media de fotogramas transmitidos al pipe por segundo durante la ventana reciente (`transmitted_en_ventana / window_s`).

*Nota*: Representan el rendimiento instantáneo de la última ventana, no un promedio histórico desde el arranque.

---

## 5. Tiempos y Latencias

### 5.1. Hitos Monotónicos (`milestones_s`)
Marcas de tiempo monotónicas registradas una sola vez al alcanzar etapas críticas:

- **Hitos del Backend** (segundos desde la recepción de la petición HTTP `connect`):
  - `connect_request_s`: 0.0 (inicio de la solicitud).
  - `athena_thread_started_s`: Inicio del hilo `AthenaThread`.
  - `process_spawn_started_s`: Inicio de la invocación de `subprocess.Popen` para el worker.
  - `process_spawned_s`: Proceso worker creado exitosamente.
  - `first_jpeg_received_buffer_s`: Registra el primer mensaje de imagen recibido desde el pipe en el buffer de Athena. Puede corresponder a un placeholder ("SIN SEÑAL"), por lo que no garantiza que se haya recibido un JPEG de cámara real.
  - `first_mjpeg_yield_s`: Registra la primera imagen entregada por el generador MJPEG al servidor web (FastAPI). También puede corresponder a un placeholder y no demuestra que el navegador haya recibido, decodificado o mostrado la imagen.

- **Hitos del Worker** (segundos desde el arranque del proceso worker):
  - `worker_started_s`: 0.0 (arranque del worker).
  - `imports_started_s` / `imports_finished_s`: Carga de librerías (`cv2`, `numpy`, detectores).
  - `*_model_load_started_s` / `*_model_load_finished_s`: Tiempos que rodean importaciones de módulos que pueden inicializar modelos de forma anticipada. Por tanto, incluyen el tiempo de importación y la inicialización que ocurra dentro de esos módulos, no exclusivamente la lectura de pesos. En `card_detector`, el import puede finalizar aunque el modelo no esté disponible, porque el error se captura y `model` queda en `None`.
  - `videocapture_open_started_s` / `videocapture_open_finished_s`: Apertura de la fuente de vídeo.
  - `first_frame_captured_s`: Primer fotograma capturado por el hilo de cámara.
  - `first_inference_completed_s`: Solo se registra cuando una inferencia esperada se ejecuta y finaliza exitosamente (ByteTrack en evasión, o detector YOLO en acceso). Puede no estar presente si el detector no llega a ejecutarse, no está disponible o falla antes de completarse.
  - `first_processing_completed_s`: Registra la finalización de la etapa de procesamiento del primer ciclo, previo a la codificación JPEG. No representa la finalización de la transmisión.
  - `first_jpeg_encoded_s`: Primera compresión JPEG exitosa.

*Aviso de sincronía*: El backend y el worker se ejecutan en procesos separados con relojes monotónicos independientes; sus marcas de tiempo no deben restarse directamente entre sí.

### 5.2. Tiempos Acumulados por Etapa (`timings_ms`)
Para cada etapa ejecutada se reporta un objeto con:
- `count`: Veces ejecutada.
- `total_ms`: Tiempo total acumulado en milisegundos.
- `max_ms`: Tiempo máximo individual registrado en milisegundos.
- `avg_ms`: Tiempo promedio por ejecución en milisegundos (`total_ms / count`).

Etapas instrumentadas:
- `videocapture_open`: Mide la creación del objeto `cv2.VideoCapture(source)`. No representa el tiempo hasta obtener el primer frame válido (lo cual se refleja en otros hitos).
- `capture_read`: Lectura física del fotograma en el hilo de captura (`cap.read()`).
- `frame_copy`: Clonación del fotograma (`frame.copy()`) bajo bloqueo de buffer.
- `frame_obtain`: Obtención del último fotograma disponible desde FastCameraReader mediante su método read(), incluyendo la recuperación de su secuencia. No realiza una segunda lectura física de VideoCapture; esa operación se mide en capture_read.
- `resize`: Redimensión lineal a 480px de ancho si la fuente supera esa resolución.
- `bgr_to_rgb`: Conversión de espacio de color para modelos que lo requieren.
- `bytetrack`: Ejecución del rastreador multiobjeto ByteTrack.
- `yolo_person`: Inferencia de personas con YOLO.
- `mediapipe_pose`: Inferencia de articulaciones corporales con MediaPipe Pose.
- `yolo_card`: Inferencia de tarjetas de acceso con YOLO.
- `tripwire_evaluation`: Evaluación geométrica del cruce de línea de evasión.
- `annotations_hud`: Agrega las anotaciones dibujadas sobre el frame (cajas, estados, etiquetas). No representa únicamente el HUD.
- `jpeg_encode`: Compresión de la imagen a formato JPEG calidad 60.
- `pipe_send_jpeg`: Escritura y vaciado (`flush`) de los bytes JPEG en el canal `stdout`.

---

## 6. Recursos del Sistema (`resources`)

El bloque `resources` expone el consumo del proceso worker mediante la librería `psutil`:

- **`available`**: Booleano. Indica `true` si `psutil` está instalado y accesible en el entorno virtual, o `false` en caso contrario.
- **`cpu_percent`**: Porcentaje de CPU consumido por el proceso worker según `psutil`, **no** el porcentaje global del sistema. La primera muestra tras el arranque puede devolver `0.0` debido a la semántica de muestreo de `psutil.Process.cpu_percent(None)`.
- **`rss_bytes`**: Memoria residente física utilizada por el subproceso worker expresada en bytes.
- **`num_threads`**: Cantidad de hilos activos en el proceso worker (hilo principal + hilo de captura + hilos auxiliares de OpenCV o runtime de ML).

*Aislamiento*: Si `psutil` no está presente o falla, se reporta `{"available": false}` sin interrumpir la captura ni la inferencia.

---

## 7. Reportes Periódicos (`emit_if_due`)

- El worker envía un mensaje binario (`MSG_METRICS = 0x03`) al backend cada vez que han transcurrido al menos 5.0 segundos desde el último resumen.
- **Dependencia estricta del ciclo principal**: `emit_if_due()` se evalúa al final de cada ciclo principal procesado. Si la cámara no abre, no hay frames procesables o el ciclo no llega a ese punto, no se emitirán reportes del worker durante ese intervalo.
- **Estado de la sesión en el backend**: La sesión diagnóstica del backend puede seguir activa (`is_active: true`) incluso sin nuevos reportes del worker.
- No se utilizan hilos auxiliares de temporización para emitir reportes, previniendo contención de bloqueos o sobrecarga del pipe. Si la fuente se detiene o el worker se reinicia, la sesión diagnóstica continúa en `AthenaThread` y los reportes se reanudan tan pronto como el nuevo subproceso worker se conecte y avance.

---

## 8. Limitaciones de la Telemetría

1. **No mide latencia de red ni renderizado de cliente**: `first_mjpeg_yield_s` mide exclusivamente la entrega de la primera imagen al generador HTTP de FastAPI (la cual puede ser un placeholder). La transmisión por red hasta el navegador, su decodificación y el renderizado final en el elemento `<img>` o `<canvas>` dependen del ancho de banda y la carga del cliente, por lo que no quedan demostrados por este hito.
2. **Volatilidad**: La telemetría no se persiste en base de datos SQLite; se almacena únicamente en la memoria RAM del servidor.
3. **Pérdida por hardware**: OpenCV no notifica fotogramas descartados por el sensor de la cámara antes del buffer del sistema operativo; únicamente se contabilizan fallos explícitos de lectura (`capture_read_failures`).
