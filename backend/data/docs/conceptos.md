# Conceptos Clave y Glosario Operativo de ARGOS - SiViA

## Cámara
Dispositivo de captura registrado en el sistema (código tipo `CAM-001`), asociado a una estación, ubicación física, estado (`activa`, `offline`, `mantenimiento`) y fuente de video (IP, RTSP, archivo o webcam).

## Evento o Detección (Análisis)
Incidencia registrada por el motor de visión artificial ante una sospecha de evasión o anomalía en torniquetes.
- Contiene: ID único, cámara asociada, tipo (`evasion`, `intrusion`, `caida`, `otro`), nivel de confianza (0.0 a 1.0), estado (`pendiente`, `confirmado`, `descartado`), ruta de evidencia y timestamps de detección y revisión.

## Alerta
Evento que se encuentra en estado `pendiente` y requiere validación visual por parte de un operador o supervisor en el centro de control.

## Nivel de Confianza (Score)
Valor decimal entre 0.0 y 1.0 (o porcentaje de 0% a 100%) generado por los modelos de visión (YOLOv8 y MediaPipe Pose) que cuantifica la certeza matemática de la detección:
- **Interpretación**: Un score del 78% significa una probabilidad alta estimada por el modelo según sus patrones de entrenamiento, pero **no equivale por sí solo a certeza absoluta ni a culpabilidad legal**. Por diseño, requiere confirmación humana por el operador antes de catalogarse como incidente confirmado.

## Evidencia Fotográfica
Captura en formato JPEG del cuadro exacto de video donde se detectó el cruce irregular. Se almacena localmente de forma protegida contra path traversal y se vincula al registro del evento.

## Control de Acceso Basado en Roles (RBAC)
Sistema que restringe las acciones y datos visibles según el rol del usuario:
- **admin**: Acceso irrestricto a todo el sistema, gestión de usuarios y matriz de permisos.
- **supervisor**: Monitoreo de cámaras, eventos, estadísticas completas y auditoría.
- **operador**: Monitoreo de cámaras asignadas, recepción de alertas en vivo y revisión de eventos (`confirmado`/`descartado`).
- **analista**: Lectura analítica de estadísticas e históricos y exportación de reportes.
- **tecnico**: Gestión física de cámaras, configuración de IA, logs técnicos y mantenimiento.
- **auditor**: Solo lectura estricta de logs de auditoría, eventos y estadísticas de cumplimiento.
