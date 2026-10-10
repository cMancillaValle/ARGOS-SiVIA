#!/usr/bin/env python3
"""
ARGOS - SiViA · Módulo de Túnel Ngrok (FastAPI + Uvicorn)
==========================================================
Expone el servidor FastAPI y el WebSocket de cámaras al exterior usando pyngrok.
Ejecutar: python ngrok_tunnel.py
"""

import os
import sys
import time
import signal
import logging
import subprocess
import urllib.request
import urllib.error

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ARGOS.Ngrok")

# ── Configuración ──────────────────────────────────────────────────────────
ARGOS_PORT    = int(os.environ.get("ARGOS_PORT", 5000))
NGROK_TOKEN   = os.environ.get("NGROK_AUTHTOKEN", "")
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR   = os.path.join(BASE_DIR, "backend")


# ══════════════════════════════════════════════════════════════════════════
#  PASO 1 - Verificar / instalar pyngrok
# ══════════════════════════════════════════════════════════════════════════
def ensure_pyngrok():
    try:
        import pyngrok  # noqa: F401
    except ImportError:
        log.warning("pyngrok no encontrado. Instalando…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok"])
        log.info("pyngrok instalado correctamente.")

ensure_pyngrok()

from pyngrok import ngrok, conf, exception as ngrok_exc  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  PASO 1.5 - Construir Widget Hermes (Micro-Frontend)
# ══════════════════════════════════════════════════════════════════════════
def build_hermes_widget():
    hermes_dir = os.path.join(BASE_DIR, "frontend-hermes")
    if os.path.exists(hermes_dir):
        log.info("Construyendo Hermes IA Widget (Micro-Frontend)...")
        try:
            subprocess.check_call("npm run build", shell=True, cwd=hermes_dir)
            log.info("Widget Hermes compilado correctamente.")
        except subprocess.CalledProcessError as e:
            log.warning(f"Advertencia: build del widget falló: {e}")

build_hermes_widget()


# ══════════════════════════════════════════════════════════════════════════
#  PASO 2 - Autenticar Ngrok
# ══════════════════════════════════════════════════════════════════════════
def autenticar_ngrok():
    token = NGROK_TOKEN

    if not token:
        token_file = os.path.join(BASE_DIR, ".ngrok_token")
        if os.path.exists(token_file):
            token = open(token_file).read().strip()

    if not token:
        log.error(
            "No se encontró NGROK_AUTHTOKEN.\n"
            "  Opciones:\n"
            "    1. export NGROK_AUTHTOKEN='tu_token'\n"
            "    2. Crea el archivo .ngrok_token con tu token\n"
            "  Obtén tu token en: https://dashboard.ngrok.com/get-started/your-authtoken"
        )
        sys.exit(1)

    ngrok.set_auth_token(token)
    log.info("Ngrok autenticado correctamente.")


# ══════════════════════════════════════════════════════════════════════════
#  PASO 3 - Iniciar FastAPI (Uvicorn) en segundo plano
# ══════════════════════════════════════════════════════════════════════════
fastapi_process = None

def iniciar_fastapi():
    global fastapi_process
    log.info(f"Iniciando FastAPI (Uvicorn) en puerto {ARGOS_PORT} (workers=1)…")

    cmd = [
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", str(ARGOS_PORT),
        "--workers", "1"
    ]

    fastapi_process = subprocess.Popen(
        cmd,
        cwd=BACKEND_DIR,
        env={**os.environ, "ARGOS_PORT": str(ARGOS_PORT)},
    )

    # Espera activa contra /api/health
    health_url = f"http://127.0.0.1:{ARGOS_PORT}/api/health"
    log.info(f"Esperando respuesta de FastAPI en {health_url}…")

    max_intentos = 30  # hasta 30 segundos
    servidor_listo = False

    for intento in range(max_intentos):
        if fastapi_process.poll() is not None:
            log.error("El proceso Uvicorn terminó inesperadamente. Revisa los logs.")
            sys.exit(1)

        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    servidor_listo = True
                    break
        except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
            pass

        time.sleep(1)

    if not servidor_listo:
        log.error("Timeout esperando inicio de FastAPI. Cerrando proceso…")
        if fastapi_process.poll() is None:
            fastapi_process.terminate()
        sys.exit(1)

    log.info(f"FastAPI activo ✓  →  http://localhost:{ARGOS_PORT}")
    return fastapi_process


# ══════════════════════════════════════════════════════════════════════════
#  PASO 4 - Abrir túnel Ngrok
# ══════════════════════════════════════════════════════════════════════════
tunnel = None

def abrir_tunel():
    global tunnel
    try:
        tunnel = ngrok.connect(
            addr=ARGOS_PORT,
            proto="http",
        )
    except ngrok_exc.PyngrokNgrokError as e:
        log.error(f"Error al abrir túnel: {e}")
        sys.exit(1)

    url_publica = tunnel.public_url
    if url_publica.startswith("http://"):
        url_publica = url_publica.replace("http://", "https://", 1)

    return url_publica


# ══════════════════════════════════════════════════════════════════════════
#  PASO 5 - Mostrar información de acceso
# ══════════════════════════════════════════════════════════════════════════
def mostrar_info(url_publica: str):
    ws_url = url_publica.replace("https://", "wss://").replace("http://", "ws://")
    ws_full = f"{ws_url}/api/camaras/client/push"

    separador = "═" * 65
    print(f"\n{separador}")
    print("  ARGOS - SiViA  ·  Acceso Remoto Activo (FastAPI + WebSocket)")
    print(separador)
    print(f"  Local:          http://localhost:{ARGOS_PORT}")
    print(f"  Público:         {url_publica}")
    print(f"  API pública:     {url_publica}/api")
    print(f"  WebSocket:       {ws_full}")
    print(f"  Inspector Ngrok: http://localhost:4040")
    print(separador)
    print("  Tanto la API REST como el WebSocket operan en el mismo túnel.")
    print(f"{separador}\n")


# ══════════════════════════════════════════════════════════════════════════
#  Cierre limpio con Ctrl+C
# ══════════════════════════════════════════════════════════════════════════
def cleanup(signum=None, frame=None):
    log.info("Cerrando ARGOS + Ngrok…")
    try:
        if tunnel:
            ngrok.disconnect(tunnel.public_url)
            ngrok.kill()
            log.info("Túnel Ngrok cerrado.")
    except Exception:
        pass
    try:
        if fastapi_process and fastapi_process.poll() is None:
            fastapi_process.terminate()
            fastapi_process.wait(timeout=5)
            log.info("FastAPI detenido.")
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT,  cleanup)
signal.signal(signal.SIGTERM, cleanup)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═"*65)
    print("  ARGOS - SiViA  ·  Iniciando con Ngrok")
    print("═"*65)

    autenticar_ngrok()
    iniciar_fastapi()
    url_publica = abrir_tunel()
    mostrar_info(url_publica)

    url_file = os.path.join(BASE_DIR, ".ngrok_url_actual")
    with open(url_file, "w") as f:
        f.write(url_publica)
    log.info(f"URL guardada en  {url_file}")

    log.info("Sistema activo. Presiona Ctrl+C para detener.")
    try:
        while True:
            time.sleep(10)
            if fastapi_process and fastapi_process.poll() is not None:
                log.error("FastAPI se detuvo inesperadamente. Cerrando…")
                cleanup()
    except KeyboardInterrupt:
        cleanup()
