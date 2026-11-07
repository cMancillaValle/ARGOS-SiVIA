"""
ARGOS - SiViA · Backend Principal (FastAPI)
──────────────────────────────────────────────────────────────────────────────
Aplicación unificada FastAPI de producción que reemplaza completamente a Flask.
Incluye:
  · API REST completa con autenticación y RBAC
  · WebSocket de ingesta de video de cámara en el mismo proceso y puerto:
      WS /api/camaras/client/push
  · Streaming de video MJPEG y eventos SSE
  · Motor Athena IA en memoria compartida
  · Rate limiting mediante slowapi
  · Servicio de evidencias protegidas contra path traversal
  · Servicio de frontend estático y Hermes
  · Integración con Ngrok y arranque local
──────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urlparse

# Asegurar que 'backend' esté en sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Cargar variables de entorno desde .env ───────────────────────────────────
try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False


def _load_env():
    env_path = os.path.normpath(os.path.join(BASE_DIR, '..', '.env'))
    if not os.path.exists(env_path):
        return
    try:
        load_dotenv(env_path, override=False)
    except Exception:
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val


_load_env()


import pathlib
import mimetypes
from services.auth_service import validate_token, tiene_permiso
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi.errors import RateLimitExceeded

from database.db import init_db, seed_db
from utils.limiter import limiter

# ── Rutas y Routers ──────────────────────────────────────────────────────────
from api.routers.auth import router as auth_router
from api.routers.cameras import router as cameras_router
from api.routers.camera_client import (
    router as camera_client_router,
    get_client_camera,
    get_client_by_camera,
    remove_client_camera,
    _client_cameras,
)
from api.routers.events import router as events_router
from api.routers.stats import router as stats_router
from api.routers.users import router as users_router
from api.routers.chat import router as chat_router
from api.routers.auditoria import router as auditoria_router
from api.routers.rbac import router as rbac_router
from api.routers.system_metrics import router as system_metrics_router
from api.routers.profile import router as profile_router
from api.routers.reset_password import router as reset_password_router
from api.routers.transmilenio import router as transmilenio_router
from api.routers.sesiones import router as sesiones_router

# ── Carpetas y Rutas del Sistema ─────────────────────────────────────────────
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend'))
HERMES_DIST  = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend-hermes', 'dist'))
DB_PATH      = os.path.normpath(os.path.join(BASE_DIR, '..', 'database', 'argos.db'))
EVIDENCE_DIR = os.path.join(BASE_DIR, 'evidence')
os.makedirs(EVIDENCE_DIR, exist_ok=True)

PORT = int(os.environ.get("ARGOS_PORT", 5000))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("argos.backend")


def _cors_origins() -> list[str]:
    """Orígenes adicionales explícitos; el frontend integrado funciona por mismo origen."""
    configured = os.environ.get('ARGOS_CORS_ORIGINS', '')
    origins = []
    for raw in configured.split(','):
        origin = raw.strip().rstrip('/')
        if not origin:
            continue
        parsed = urlparse(origin)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path not in ('', '/'):
            logger.warning('Origen CORS ignorado por formato inválido: %s', origin)
            continue
        if '*' in origin:
            logger.warning('Origen CORS ignorado porque contiene comodín: %s', origin)
            continue
        if origin not in origins:
            origins.append(origin)
    return origins


# ── Lifespan de FastAPI ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización en arranque
    logger.info("Iniciando ARGOS-SiViA Backend (FastAPI)...")
    if os.environ.get('ARGOS_DEV_MODE', '').strip().lower() in ('1', 'true', 'yes'):
        logger.warning(
            'ARGOS_DEV_MODE está activo: los códigos de verificación se incluyen en respuestas de pruebas. '
            'No use este modo en despliegues públicos.'
        )
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db(DB_PATH)
    seed_db(DB_PATH)
    logger.info(f"Base de datos SQLite lista en: {DB_PATH}")

    yield

    # Cierre limpio
    logger.info("Deteniendo ARGOS-SiViA Backend...")
    try:
        from core_ia.athena.athena_engine import athena
        if athena:
            athena.stop_all()
    except Exception as e:
        logger.warning(f"Error al detener Athena: {e}")


app = FastAPI(
    title="ARGOS - SiViA",
    version="1.7.5",
    description="Sistema Inteligente de Vigilancia y Alerta con Athena IA",
    lifespan=lifespan
)

# Conectar rate limiter de slowapi a la app
app.state.limiter = limiter


# ── CORS Middleware ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Token"],
)


# ── Handlers Globales de Excepción ───────────────────────────────────────────
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={'error': 'Demasiados intentos. Has sido bloqueado temporalmente por seguridad. Intenta nuevamente en 1 minuto.'}
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 429:
        return JSONResponse(
            status_code=429,
            content={'error': 'Demasiados intentos. Has sido bloqueado temporalmente por seguridad. Intenta nuevamente en 1 minuto.'}
        )
    if exc.status_code == 401:
        msg = exc.detail if isinstance(exc.detail, (str, dict)) else 'No autorizado.'
        return JSONResponse(status_code=401, content={'error': msg} if isinstance(msg, str) else msg)
    if exc.status_code == 403:
        msg = exc.detail if isinstance(exc.detail, (str, dict)) else 'Acceso denegado.'
        return JSONResponse(status_code=403, content={'error': msg} if isinstance(msg, str) else msg)
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content={'error': exc.detail or 'Recurso no encontrado.'})

    detail = exc.detail if isinstance(exc.detail, (str, dict)) else str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={'error': detail} if isinstance(detail, str) else detail)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error interno no controlado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={'error': 'Error interno del servidor. Por favor, intenta de nuevo.'}
    )


# ── Registro de Routers API ──────────────────────────────────────────────────
app.include_router(auth_router,           prefix="/api/auth", tags=["auth"])
app.include_router(cameras_router,        prefix="/api/camaras", tags=["cameras"])
app.include_router(camera_client_router,  prefix="/api/camaras", tags=["camera_client"])  # WS /api/camaras/client/push
app.include_router(events_router,         prefix="/api/eventos", tags=["events"])
app.include_router(stats_router,          prefix="/api/stats", tags=["stats"])
app.include_router(users_router,          prefix="/api/usuarios", tags=["users"])
app.include_router(chat_router,           prefix="/api/chat", tags=["chat"])
app.include_router(auditoria_router,      prefix="/api/auditoria", tags=["auditoria"])
app.include_router(rbac_router,           prefix="/api/rbac", tags=["rbac"])
app.include_router(system_metrics_router, prefix="/api/sistema", tags=["system"])
app.include_router(profile_router,        prefix="/api/perfil", tags=["profile"])
app.include_router(reset_password_router, prefix="/api/auth/reset-password", tags=["reset_password"])
app.include_router(transmilenio_router,   prefix="/api/transmilenio", tags=["transmilenio"])
app.include_router(sesiones_router,       prefix="/api/sesiones", tags=["sesiones"])


# ── Rutas de Salud (Healthcheck) ─────────────────────────────────────────────
@app.get("/health")
@app.get("/api")
@app.get("/api/health")
def health():
    return {
        'sistema': 'ARGOS - SiViA',
        'version': '1.7.5',
        'estado': 'activo',
        'framework': 'FastAPI',
        'endpoints': [
            'POST /api/auth/login',
            'GET  /api/camaras',
            'GET  /api/eventos',
            'GET  /api/stats',
            'POST /api/chat',
            'GET  /api/rbac/permisos',
            'GET  /api/rbac/modulos',
            'POST /api/rbac/verificar',
            'GET  /api/camaras/evidencia/{filepath:path}',
            'WS   /api/camaras/client/push',
        ]
    }


# ── Evidencias con Protección contra Path Traversal ──────────────────────────
@app.get("/api/camaras/evidencia/{filepath:path}")
@app.get("/api/evidencia/{filepath:path}")
def get_evidencia(filepath: str, request: Request):
    """
    Sirve las imágenes de evidencia guardadas por capture_manager.
    Protecciones:
    1. Autenticación y RBAC (permiso eventos:ver o camaras:ver) mediante cabecera X-Token.
    2. Prevención rigurosa de Path Traversal mediante resolución canónica y comprobación is_relative_to().
    3. Bloqueo de rutas absolutas, enlaces simbólicos fuera del directorio y extensiones no permitidas.
    4. Tipado MIME estricto sin filtrado de rutas internas.
    """
    token = request.headers.get("X-Token")
    if not token:
        raise HTTPException(status_code=401, detail="Autenticación requerida para acceder a evidencias.")

    user = validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    if not (tiene_permiso(user, "eventos:ver") or tiene_permiso(user, "camaras:ver")):
        raise HTTPException(
            status_code=403,
            detail={"error": "Acceso denegado.", "permiso_requerido": "eventos:ver"}
        )

    # Sanitización y resolución segura de rutas
    clean_fp = filepath.replace('\\', '/').strip('/')
    if clean_fp.startswith('evidence/'):
        clean_fp = clean_fp[len('evidence/'):]

    base_evidence_path = pathlib.Path(EVIDENCE_DIR).resolve()
    target_candidate = (base_evidence_path / clean_fp).resolve()

    # Comprobación de que la ruta resuelta reside estrictamente dentro de EVIDENCE_DIR
    try:
        is_inside = target_candidate.is_relative_to(base_evidence_path)
    except AttributeError:
        try:
            target_candidate.relative_to(base_evidence_path)
            is_inside = True
        except ValueError:
            is_inside = False

    if not is_inside or target_candidate == base_evidence_path:
        raise HTTPException(status_code=403, detail="Acceso denegado: ruta no autorizada.")

    # Restricción de extensiones permitidas
    if target_candidate.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
        raise HTTPException(status_code=403, detail="Tipo de archivo no permitido.")

    if not target_candidate.is_file():
        raise HTTPException(status_code=404, detail="Archivo de evidencia no encontrado.")

    mime_type, _ = mimetypes.guess_type(str(target_candidate))
    if not mime_type:
        mime_type = "image/jpeg"

    return FileResponse(
        str(target_candidate),
        media_type=mime_type,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
        }
    )


# ── Páginas del Frontend ─────────────────────────────────────────────────────
@app.get("/")
def index_page():
    index_path = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"message": "ARGOS-SiViA Frontend no encontrado"}


@app.get("/login")
def login_page():
    login_path = os.path.join(FRONTEND_DIR, 'login.html')
    if os.path.isfile(login_path):
        return FileResponse(login_path)
    raise HTTPException(status_code=404, detail="login.html no encontrado")


@app.get("/dashboard")
def dashboard_page():
    dash_path = os.path.join(FRONTEND_DIR, 'dashboard.html')
    if os.path.isfile(dash_path):
        return FileResponse(dash_path)
    raise HTTPException(status_code=404, detail="dashboard.html no encontrado")


@app.get("/hermes/{filename:path}")
def hermes_static(filename: str):
    full_path = os.path.normpath(os.path.join(HERMES_DIST, filename))
    if not os.path.abspath(full_path).startswith(os.path.abspath(HERMES_DIST)):
        raise HTTPException(status_code=403, detail="Acceso denegado")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="Archivo Hermes no encontrado")
    return FileResponse(full_path)


# Montar archivos estáticos del frontend (css, js, assets, etc.)
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=False), name="frontend_static")


if __name__ == "__main__":
    import uvicorn
    print('\n' + '═'*56)
    print('  ARGOS - SiViA  ·  Backend V1.7.5 (FastAPI + Athena IA)')
    print('═'*56)
    print(f'  🌐  Local:      http://localhost:{PORT}')
    print(f'  📡  API:        http://localhost:{PORT}/api')
    print(f'  🎥  Stream:     http://localhost:{PORT}/api/camaras/<id>/stream')
    print(f'  📹  WebSocket:  ws://localhost:{PORT}/api/camaras/client/push')
    print(f'  🔐  RBAC:       http://localhost:{PORT}/api/rbac/matriz')
    print(f'  🤖  IA Cfg:     http://localhost:{PORT}/api/sistema/ia-config')
    print('═'*56 + '\n')
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, workers=1, reload=False)
