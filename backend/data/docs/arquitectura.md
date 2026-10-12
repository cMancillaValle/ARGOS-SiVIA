# Arquitectura del Sistema ARGOS - SiViA

## Visión General
ARGOS - SiViA es una plataforma de monitoreo inteligente para transporte público masivo (TransMilenio), orientada a la detección automática de accesos no autorizados y evasión de pasaje mediante visión artificial.

## Componentes Principales
1. **Backend ASGI (FastAPI + Uvicorn)**:
   - Proporciona la API REST unificada en el puerto configurado (por defecto 5000).
   - Ejecuta en un único worker para compartir memoria local y locks de sincronización con Athena.
   - Maneja WebSockets nativos en `WS /api/camaras/client/push` para ingesta de fotogramas de cámaras web remotas.
   - Entrega streaming de video MJPEG (`StreamingResponse`) y eventos en tiempo real mediante Server-Sent Events (SSE).
   - Implementa rate limiting con `slowapi` y control de acceso basado en roles (RBAC).

2. **Base de Datos Relacional (SQLite)**:
   - Archivo local único en `database/argos.db`.
   - Entidades principales: `usuarios`, `sesiones`, `camaras`, `eventos`, `auditoria` y `configuracion`.
   - Todas las consultas de datos son locales, parametrizadas y ejecutadas con control de permisos previo.

3. **Motor de Visión Artificial (Athena IA)**:
   - Proceso independiente de inferencia que procesa fuentes RTSP, cámaras locales o buffers en memoria.
   - Involucra modelos YOLOv8 para detección de personas y MediaPipe Pose para biomecánica.
   - Se comunica con el backend mediante colas y buffers de memoria compartida (`client_buffer`).

4. **Frontend y Micro-Frontend**:
   - Dashboard principal en SPA modular (HTML5 / Vanilla JavaScript).
   - Asistente conversacional Hermes implementado como micro-frontend en React + TypeScript (Vite).
