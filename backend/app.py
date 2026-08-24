"""
ARGOS - SiViA · Backend  (app.py actualizado con RBAC)
------------------------------------------------------
Cambios respecto a la versión anterior:
  · Registra el nuevo blueprint rbac_bp  en /api/rbac
  · Todo lo demás permanece igual
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

# ── Cargar variables de entorno desde .env ───────────────────────────────────
try:
    from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
except ImportError:  # python-dotenv no está instalado
    def load_dotenv(*_args, **_kwargs):
        return False


def _load_env():
    """Lee el .env de la raíz del proyecto e inyecta en os.environ (sin sobreescribir)."""
    env_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '.env'))
    if not os.path.exists(env_path):
        return
    try:
        load_dotenv(env_path, override=False)
    except Exception:
        # Fallback: leer manualmente
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


from flask import Flask, jsonify, send_from_directory
from database.db import init_db, seed_db
from routes.auth       import auth_bp
from routes.cameras    import cameras_bp
from routes.events     import events_bp
from routes.stats      import stats_bp
from routes.users      import users_bp
from routes.chat            import chat_bp
from routes.auditoria       import auditoria_bp
from routes.rbac_api        import rbac_bp
from routes.system_metrics  import system_metrics_bp
from routes.profile         import profile_bp
from routes.reset_password  import reset_bp
from routes.camera_client   import camera_client_bp, init_websocket
from utils.limiter          import limiter
from flask_sock             import Sock
import logging


BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend'))
DB_PATH      = os.path.normpath(os.path.join(BASE_DIR, '..', 'database', 'argos.db'))

# Puerto configurable via variable de entorno (requerido por ngrok_tunnel.py)
PORT = int(os.environ.get("ARGOS_PORT", 5000))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.secret_key = os.environ.get("SECRET_KEY", "argos-sivia-secret-2025")

# Inicializar flask-sock para WebSocket (camara cliente remota)
sock = Sock(app)
init_websocket(sock)

# Inicializar limiter
limiter.init_app(app)

from werkzeug.exceptions import HTTPException

@app.errorhandler(Exception)
def handle_global_error(e):
    # Atrapar excepciones HTTP (como 429 Too Many Requests del Limiter, 404, etc.)
    if isinstance(e, HTTPException):
        if e.code == 429:
            return jsonify({'error': 'Demasiados intentos. Has sido bloqueado temporalmente por seguridad. Intenta nuevamente en 1 minuto.'}), 429
        return jsonify({'error': e.description}), e.code
        
    # Loggear internamente el error pero nunca enviarlo crudo al cliente final
    logging.error(f"Error interno: {e}", exc_info=True)
    return jsonify({'error': 'Error interno del servidor. Por favor, intenta de nuevo.'}), 500


@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,X-Token'
    return r

@app.before_request
def handle_preflight():
    from flask import request, Response
    if request.method == 'OPTIONS':
        r = Response()
        r.headers['Access-Control-Allow-Origin']  = '*'
        r.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type,X-Token'
        return r

# ── Blueprints ──────────────────────────────────────────────────
app.register_blueprint(auth_bp,           url_prefix='/api/auth')
app.register_blueprint(cameras_bp,        url_prefix='/api/camaras')
app.register_blueprint(camera_client_bp,  url_prefix='/api/camaras')
app.register_blueprint(events_bp,         url_prefix='/api/eventos')
app.register_blueprint(stats_bp,          url_prefix='/api/stats')
app.register_blueprint(users_bp,          url_prefix='/api/usuarios')
app.register_blueprint(chat_bp,           url_prefix='/api/chat')
app.register_blueprint(auditoria_bp,      url_prefix='/api/auditoria')
app.register_blueprint(rbac_bp,           url_prefix='/api/rbac')
app.register_blueprint(system_metrics_bp, url_prefix='/api/sistema')
app.register_blueprint(profile_bp,        url_prefix='/api/perfil')
app.register_blueprint(reset_bp,          url_prefix='/api/auth/reset-password')

# ── Frontend ────────────────────────────────────────────────────
HERMES_DIST = os.path.normpath(os.path.join(BASE_DIR, '..', 'frontend-hermes', 'dist'))

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/hermes/<path:filename>')
def hermes_static(filename):
    return send_from_directory(HERMES_DIST, filename)

@app.route('/login')
def login_page():
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/dashboard')
def dashboard_page():
    return send_from_directory(FRONTEND_DIR, 'dashboard.html')

# ── Health ──────────────────────────────────────────────────────
@app.route('/api')
@app.route('/api/health')   # alias para el indicador del login
def health():
    return jsonify({
        'sistema': 'ARGOS - SiViA', 'version': '1.7.5', 'estado': 'activo',
        'endpoints': [
            'POST /api/auth/login',
            'GET  /api/camaras',
            'GET  /api/eventos',
            'GET  /api/stats',
            'POST /api/chat',
            'GET  /api/rbac/permisos',
            'GET  /api/rbac/modulos',
            'POST /api/rbac/verificar',
        ]
    })

if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db(DB_PATH)
    seed_db(DB_PATH)
    print('\n' + '═'*56)
    print('  ARGOS - SiViA  ·  Backend V1.7.5 (RBAC + Athena IA)')
    print('═'*56)
    print(f'  🌐  Local:   http://localhost:{PORT}')
    print(f'  📡  API:     http://localhost:{PORT}/api')
    print(f'  🎥  Stream:  http://localhost:{PORT}/api/camaras/stream')
    print(f'  🔐  RBAC:    http://localhost:{PORT}/api/rbac/matriz')
    print(f'  🤖  IA Cfg:  http://localhost:{PORT}/api/sistema/ia-config')
    print('═'*56 + '\n')
    app.run(host='0.0.0.0', debug=True, port=PORT, threaded=True, use_reloader=False)

