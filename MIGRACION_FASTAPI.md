# Informe Técnico de Migración: Flask → FastAPI en ARGOS-SiViA

**Versión:** 1.7.5  
**Fecha:** 2026-10-09  
**Plataforma:** ARGOS - SiViA (Sistema Inteligente de Vigilancia y Alerta)  
**Autor:** Antigravity AI Pair Programmer & DeepMind Team  

---

## 1. Motivación y Alcance

El sistema ARGOS-SiViA utilizaba originalmente Flask como framework web síncrono acoplado a `Flask-Sock`, `Flask-Limiter` y `flask-cors`. Con la integración de la transmisión continua de video en tiempo real desde navegadores cliente y el motor Athena IA, surgieron los siguientes desafíos arquitectónicos:
- **Gestión Asíncrona Concurrente:** El WebSocket requería una pila ASGI nativa de alto rendimiento y bajo overhead.
- **Unificación de Proceso y Memoria:** El buffer de fotogramas (`client_buffer`) y el motor de inferencia Athena operan en la memoria local del proceso con primitivas de sincronización (`threading.Lock`). Separar el WebSocket en un servidor o puerto distinto rompía el acceso a la memoria compartida o requería IPC complejo.
- **Modernización y Estandarización:** FastAPI aporta tipado estático, inyección de dependencias (`Depends`), modelos Pydantic, manejo asíncrono y compatibilidad OpenAPI nativa.

**Alcance de la entrega:**
- Reemplazo del 100% de Flask por FastAPI.
- Servidor de producción único en `backend/main.py` ejecutado en el puerto configurable `ARGOS_PORT` (por defecto `5000`) con un único worker (`--workers 1`).
- Integración completa del WebSocket de cámaras en `WS /api/camaras/client/push` dentro del mismo proceso y puerto.
- Eliminación de todas las dependencias productivas de Flask (`Flask`, `Flask-Cors`, `Flask-Limiter`, `flask-sock`).
- Preservación íntegra de la base de datos SQLite (`database/argos.db`), el motor Athena IA y la compatibilidad con el frontend.

---

## 2. Mapeo de Archivos: Flask (Legacy) vs. FastAPI (Moderno)

| Componente | Archivo Flask Legacy (Archivado) | Archivo FastAPI Producción | Rol / Responsabilidad |
|---|---|---|---|
| **Punto de entrada** | `backend/app.py` | `backend/main.py` | App ASGI, lifespan, CORS, error handlers, static files |
| **Autenticación** | `backend/routes/auth.py` | `backend/api/routers/auth.py` | Registro, login, 2FA, logout, `/me` |
| **Cámaras CRUD & IA** | `backend/routes/cameras.py` | `backend/api/routers/cameras.py` | CRUD, connect/disconnect Athena, MJPEG stream, SSE stream, videos |
| **WebSocket Cámaras** | `backend/routes/camera_client.py` | `backend/api/routers/camera_client.py` | `WS /api/camaras/client/push`, status y MJPEG de cliente |
| **Eventos IA** | `backend/routes/events.py` | `backend/api/routers/events.py` | Consulta, creación y confirmación/descarte de eventos |
| **Estadísticas** | `backend/routes/stats.py` | `backend/api/routers/stats.py` | Métricas de detección, eventos de hoy y resumen |
| **Usuarios** | `backend/routes/users.py` | `backend/api/routers/users.py` | Gestión administrativa de usuarios y contraseñas |
| **Perfil** | `backend/routes/profile.py` | `backend/api/routers/profile.py` | Perfil, avatar, flujo 3 pasos de email y activación 2FA |
| **RBAC** | `backend/routes/rbac_api.py` | `backend/api/routers/rbac.py` | Catálogo de permisos, módulos accesibles y matriz |
| **Reset Password** | `backend/routes/reset_password.py` | `backend/api/routers/reset_password.py` | Solicitud y confirmación de reset por correo con rate limit |
| **Auditoría** | `backend/routes/auditoria.py` | `backend/api/routers/auditoria.py` | Log de auditoría, filtros, stats y exportación CSV |
| **Chat Hermes** | `backend/routes/chat.py` | `backend/api/routers/chat.py` | Asistente conversacional Hermes IA y consulta de permisos |
| **TransMilenio** | `backend/routes/transmilenio.py` | `backend/api/routers/transmilenio.py` | Troncales, estaciones y riesgo georreferenciado |
| **Sesiones** | `backend/routes/sesiones.py` | `backend/api/routers/sesiones.py` | Usuarios conectados en tiempo real y módulo activo |
| **Sistema & Métricas** | `backend/routes/system_metrics.py` | `backend/api/routers/system_metrics.py` | CPU, RAM, disco, GPU y configuración del umbral IA |
| **Servicio Auth** | `backend/services/auth_service.py` | `backend/services/auth_service.py` | Desacoplado: añade `get_current_user`, `require_permission` |
| **Servicio RBAC** | `backend/services/rbac.py` | `backend/services/rbac.py` | Desacoplado: funciones puras sin Flask request |
| **Validador** | `backend/utils/validators.py` | `backend/utils/validators.py` | `format_error()` retorna `JSONResponse` de FastAPI |
| **Rate Limiter** | `backend/utils/limiter.py` | `backend/utils/limiter.py` | Migrado a `slowapi` con limitación basada en IP |
| **Túnel Ngrok** | `ngrok_tunnel.py` | `ngrok_tunnel.py` | Monitorea Uvicorn con healthcheck activo y túnel HTTP+WS |
| **Inicio rápido** | `start.py` | `start.py` | Lanza `uvicorn main:app --workers 1` |

*Nota:* Los archivos originales de Flask se respaldaron de manera segura en `backend/archived_legacy_flask/` con fines históricos.

---

## 3. Mapeo de Endpoints y Contratos de la API

Todos los endpoints HTTP conservaron rigurosamente sus URLs, códigos de estado y contratos JSON:

| Método | Endpoint | Permiso Requerido | Descripción |
|---|---|---|---|
| `GET` | `/api/health` | Público | Verificación del estado del servidor |
| `POST` | `/api/auth/login` | Público (Rate Limit 5/min) | Autenticación de usuario / inicio 2FA |
| `POST` | `/api/auth/login-2fa` | Público (Rate Limit 5/min) | Validación de código TOTP / backup code |
| `POST` | `/api/auth/logout` | Autenticado | Revocación del token de sesión |
| `GET` | `/api/auth/me` | Autenticado | Datos del usuario conectado |
| `GET` | `/api/camaras` | `camaras:ver` | Listado de cámaras registradas |
| `POST` | `/api/camaras` | `camaras:crear` | Registro de nueva cámara |
| `GET` | `/api/camaras/{id}` | `camaras:ver_detalle` | Detalle técnico de la cámara |
| `PUT` | `/api/camaras/{id}` | `camaras:editar` | Actualización de parámetros |
| `DELETE` | `/api/camaras/{id}` | `camaras:eliminar` | Eliminación de cámara y parada de Athena |
| `POST` | `/api/camaras/{id}/connect` | Autenticado | Inicio de inferencia de Athena para la cámara |
| `POST` | `/api/camaras/{id}/disconnect` | Autenticado | Detención de inferencia de Athena |
| `GET` | `/api/camaras/{id}/stream` | Autenticado (`?t=` o `X-Token`) | Streaming MJPEG procesado por Athena |
| `GET` | `/api/camaras/eventos/stream` | Autenticado (`?t=` o `X-Token`) | Stream SSE en tiempo real de detecciones |
| `WS` | `/api/camaras/client/push` | Autenticado (Handshake) | Ingesta continua de frames de cámara cliente |
| `GET` | `/api/camaras/evidencia/{path}` | Público (Safe Path) | Entrega de capturas protegida contra traversal |
| `GET` | `/api/eventos` | `eventos:ver` | Consulta de eventos con filtros |
| `PUT` | `/api/eventos/{id}/estado` | `eventos:revisar` | Confirmar o descartar evento |
| `GET` | `/api/stats` | Autenticado | Estadísticas generales y precisión del modelo |
| `GET` | `/api/stats/hoy` | Autenticado | Eventos y estaciones críticas de las últimas 24h |
| `GET` | `/api/rbac/permisos` | Autenticado | Lista de permisos del usuario actual |
| `GET` | `/api/rbac/matriz` | Rol `admin` | Matriz de permisos completa |
| `GET` | `/api/sistema/metricas` | `sistema:ver_estado` | Snapshot de CPU, RAM, disco y GPU |
| `GET` | `/api/transmilenio/estaciones` | Autenticado | Integración cartográfica de estaciones y riesgo |
| `POST` | `/api/chat` | Autenticado | Procesamiento de intenciones en Hermes IA |

---

## 4. Protocolo WebSocket de Cámara Integrado

El WebSocket opera en `WS /api/camaras/client/push` bajo el ciclo de vida de FastAPI:

1. **Conexión y Handshake (Timeout 10s):**
   - El cliente envía:
     ```json
     { "token": "<token-sesion>", "cam_id": 1 }
     ```
   - La validación del token SQLite se ejecuta en un hilo de trabajo mediante `starlette.concurrency.run_in_threadpool(validate_token, token)`.
   - Respuesta exitosa:
     ```json
     { "type": "ok", "client_id": "<id-8-chars>", "cam_id": 1 }
     ```
   - Respuestas de error con cierre de socket:
     `{"type": "error", "message": "No autorizado"}`
     `{"type": "error", "message": "cam_id requerido"}`

2. **Ingesta de Fotogramas:**
   - Mensaje del cliente:
     ```json
     { "type": "frame", "data": "data:image/jpeg;base64,...", "ts": 1727480000000 }
     ```
   - Decodificación y escritura directa en el singleton `core_ia.athena.client_frame_buffer.client_buffer`.

3. **Latido de Control (Ping / Pong):**
   - Entrada: `{"type": "ping"}`
   - Salida: `{"type": "pong"}`

4. **Desconexión y Limpieza Automática:**
   - Al cerrar la conexión (normal o timeout de 30s de inactividad), se remueve el cliente de `client_buffer` y del diccionario en memoria `_client_cameras`.

---

## 5. Lifespan y Dependencias

FastAPI utiliza el context manager `lifespan`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db(DB_PATH)
    seed_db(DB_PATH)
    yield
    # Limpieza:
    athena.stop_all()
```

### Inyección de Dependencias
- `get_current_user`: Lee el token desde `X-Token`, valida la sesión contra SQLite y devuelve el diccionario del usuario.
- `require_permission(permiso)`: Valida que el rol del usuario contenga el permiso necesario en `PERMISOS_ROL`. Lanza `HTTP 403` si no está autorizado.
- `require_role(roles)`: Exige roles específicos (ej. `admin` para la matriz RBAC).

---

## 6. Comandos de Ejecución

### Inicio Local Directo con Uvicorn
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 5000 --workers 1
```

### Inicio mediante Script Rápido
```bash
python start.py
```

### Inicio con Túnel Remoto Ngrok
```bash
python ngrok_tunnel.py
```

### Inicio con Docker Compose
```bash
docker compose up -d
```

---

## 7. Verificación de Cero Dependencias Flask

Ejecutando la búsqueda sobre todo el código fuente productivo en `backend/`:
```bash
Get-ChildItem -Path "backend" -Recurse -Filter "*.py" | Where-Object { $_.FullName -notmatch "archived_legacy_flask" } | Select-String "from flask|import flask|flask_sock|flask_limiter|from flask_cors"
```
**Resultado:** 0 coincidencias. Ningún archivo productivo importa Flask ni sus extensiones.

Los paquetes `Flask`, `Flask-Cors`, `Flask-Limiter` y `flask-sock` han sido desinstalados completamente del entorno virtual `backend_env`.

---

## 8. Resultados de la Suite de Pruebas Automatizadas

Se ejecutó la suite completa de pruebas en `tests/test_fastapi_backend.py` con `pytest`:

```text
============================= test session starts =============================
platform win32 -- Python 3.10.5, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\yhonny\Desktop\Proyectos\ARGOS-SiVIA_v1.7.5
plugins: anyio-4.15.1
collected 13 items

tests/test_fastapi_backend.py::test_healthcheck PASSED                   [  7%]
tests/test_fastapi_backend.py::test_login_invalid PASSED                 [ 15%]
tests/test_fastapi_backend.py::test_auth_me_and_logout PASSED            [ 23%]
tests/test_fastapi_backend.py::test_rbac_permisos_y_matriz PASSED        [ 30%]
tests/test_fastapi_backend.py::test_camaras_crud PASSED                  [ 38%]
tests/test_fastapi_backend.py::test_eventos_flow PASSED                  [ 46%]
tests/test_fastapi_backend.py::test_perfil_y_sesiones PASSED             [ 53%]
tests/test_fastapi_backend.py::test_stats PASSED                         [ 61%]
tests/test_fastapi_backend.py::test_evidencias_path_traversal PASSED     [ 69%]
tests/test_fastapi_backend.py::test_videos_list PASSED                   [ 76%]
tests/test_fastapi_backend.py::test_websocket_camera_push_flow PASSED    [ 84%]
tests/test_fastapi_backend.py::test_mjpeg_and_sse_auth PASSED            [ 92%]
tests/test_fastapi_backend.py::test_ngrok_script_consistency PASSED      [100%]

======================== 13 passed, 1 warning in 4.66s ========================
```

Adicionalmente, se ejecutó la suite de prueba in-process del WebSocket (`backend/fastapi_poc/test_client.py`):
```text
========================================================
 EJECUTANDO SUITE DE PRUEBAS EN MODO IN-PROCESS (FastAPI)
========================================================
 [OK] GET /health responde HTTP 200 OK
 [OK] Rechazado con mensaje 'No autorizado' correctamente
 [OK] Rechazado con mensaje 'cam_id requerido' correctamente
 [OK] Handshake OK, client_id asignado
 [OK] Mapa _client_cameras verificado
 [OK] Ping/Pong exitoso
 [OK] Frame Base64 recibido y decodificado en client_buffer (149 bytes)
 [OK] Limpieza exitosa: cliente removido de client_buffer y mapa de cámaras al desconectar
========================================================
 TODOS LOS TESTS PASARON EXITOSAMENTE (100% COMPATIBLE)
========================================================
```

---

## 9. Conclusión

La migración ha sido completada en su totalidad con éxito. El backend de ARGOS-SiViA opera ahora de forma nativa sobre FastAPI y Uvicorn con un único puerto y proceso, compartiendo memoria fluida con Athena IA, con soporte asíncrono para WebSockets, y manteniendo total retrocompatibilidad con la base de datos, los contratos de API y el frontend existente.
