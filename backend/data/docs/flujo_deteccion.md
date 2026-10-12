# Flujo de Detección de Evasión en Athena IA

## Pipeline de Procesamiento
El motor Athena analiza el flujo de video cuadro a cuadro a través de etapas secuenciales:

1. **Captura y Normalización de Frames**:
   - Los cuadros provienen de streams RTSP, archivos de video locales o del WebSocket de cámara web (`client_buffer`).
   - Se escalan adaptativamente a 480px para optimizar el tiempo de inferencia sin perder resolución de seguimiento.

2. **Detección y Tracking de Personas**:
   - Modelo de red neuronal: **YOLOv8n** optimizado con PyTorch.
   - Algoritmo de seguimiento: **ByteTrack** asigna IDs numéricos persistentes a cada persona en escena y traza sus vectores de movimiento.

3. **Intersección con Línea Virtual (Tripwire)**:
   - Se define una línea virtual de control (`tripwire`, configurable entre 0.1 y 0.9 en la escena) que delimita la barrera de torniquetes.
   - Cuando el centroide de una persona cruza el tripwire en sentido no permitido sin validar pasaje, se activa la verificación biomecánica.

4. **Clasificación Biomecánica de Postura**:
   - Se aplica **MediaPipe Pose Lite** condicionalmente solo cuando hay personas en la zona crítica.
   - Categorías de evasión detectadas:
     - **SALTO**: Elevación anómala de rodillas por encima de la cadera al sobrepasar la barrera.
     - **AGACHADO**: Paso por debajo del torniquete (cabeza a nivel o por debajo de la cadera).
     - **CRUCE**: Paso no autorizado directo sin validación previa.

5. **Generación de Evidencia y Registro**:
   - Si la confianza calculada supera el umbral configurado (`ia_confidence_threshold`, por defecto 0.50), se captura una imagen JPEG de evidencia en `backend/evidence/`.
   - Se inserta un registro en la tabla `eventos` de SQLite con estado inicial `pendiente`.
   - Se emite una notificación al bus SSE para los operadores conectados.
