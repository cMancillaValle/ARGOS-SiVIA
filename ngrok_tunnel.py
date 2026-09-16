#!/usr/bin/env python3
"""
ARGOS - SiViA · Módulo de Túnel Ngrok
======================================
Expone el servidor Flask al exterior usando pyngrok.
Ejecutar: python ngrok_tunnel.py
"""

import os
import sys
import time
import signal
import logging
import subprocess
import threading

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("ARGOS.Ngrok")

# ── Configuración ──────────────────────────────────────────────────────────
FLASK_PORT    = int(os.environ.get("ARGOS_PORT", 5000))
NGROK_TOKEN   = os.environ.get("NGROK_AUTHTOKEN", "")   # token ngrok
# NGROK_REGION  = os.environ.get("NGROK_REGION", "sa")    # sa = South America
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
    """
    Prioridad de búsqueda del token:
      1. Variable de entorno  NGROK_AUTHTOKEN
      2. Constante NGROK_TOKEN definida arriba
      3. Archivo  .ngrok_token  en la raíz del proyecto
    """
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
            "    2. Crea el archivo  .ngrok_token  con tu token\n"
            "    3. Edita NGROK_TOKEN en ngrok_tunnel.py\n"
            "  Obtén tu token en: https://dashboard.ngrok.com/get-started/your-authtoken"
        )
        sys.exit(1)

    ngrok.set_auth_token(token)
    log.info("Ngrok autenticado correctamente.")


# ══════════════════════════════════════════════════════════════════════════
#  PASO 3 - Iniciar Flask en segundo plano
# ══════════════════════════════════════════════════════════════════════════
flask_process = None

def iniciar_flask():
    global flask_process
    app_path = os.path.join(BACKEND_DIR, "app.py")
    log.info(f"Iniciando Flask en puerto {FLASK_PORT}…")

    flask_process = subprocess.Popen(
        [sys.executable, app_path],
        cwd=BACKEND_DIR,
        env={**os.environ, "ARGOS_PORT": str(FLASK_PORT)},
    )

    # Esperar a que Flask levante
    time.sleep(2)

    if flask_process.poll() is not None:
        log.error("Flask no pudo iniciar. Revisa los logs.")
        sys.exit(1)

    log.info(f"Flask activo  →  http://localhost:{FLASK_PORT}")
    return flask_process


# ══════════════════════════════════════════════════════════════════════════
#  PASO 4 - Abrir túnel Ngrok
# ══════════════════════════════════════════════════════════════════════════
tunnel = None

def abrir_tunel():
    global tunnel
    # log.info(f"Abriendo túnel Ngrok  (región: {NGROK_REGION})…")

    try:
        tunnel = ngrok.connect(
            addr=FLASK_PORT,
            proto="http",
        )
    except ngrok_exc.PyngrokNgrokError as e:
        log.error(f"Error al abrir túnel: {e}")
        sys.exit(1)

    url_publica = tunnel.public_url
    # Preferir HTTPS si está disponible
    if url_publica.startswith("http://"):
        url_publica = url_publica.replace("http://", "https://", 1)

    return url_publica


# ══════════════════════════════════════════════════════════════════════════
#  PASO 5 - Mostrar información de acceso
# ══════════════════════════════════════════════════════════════════════════
def mostrar_info(url_publica: str):
    separador = "═" * 60
    print(f"\n{separador}")
    print("  ARGOS - SiViA  ·  Acceso Remoto Activo")
    print(separador)
    print(f"  🏠  Local:       http://localhost:{FLASK_PORT}")
    print(f"  🌍  Público:     {url_publica}")
    print(f"  📡  API pública: {url_publica}/api")
    print(f"  🔌  Inspector:   http://localhost:4040   (Ngrok dashboard)")
    print(separador)
    print("  Comparte la URL pública con otros dispositivos.")
    print("  La URL cambia cada vez que reinicias el túnel.")
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
        if flask_process and flask_process.poll() is None:
            flask_process.terminate()
            flask_process.wait(timeout=5)
            log.info("Flask detenido.")
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT,  cleanup)
signal.signal(signal.SIGTERM, cleanup)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  ARGOS - SiViA  ·  Iniciando con Ngrok")
    print("═"*60)

    autenticar_ngrok()
    iniciar_flask()
    url_publica = abrir_tunel()
    mostrar_info(url_publica)

    # ── Guardar URL en archivo para que otros scripts la consuman ──
    url_file = os.path.join(BASE_DIR, ".ngrok_url_actual")
    with open(url_file, "w") as f:
        f.write(url_publica)
    log.info(f"URL guardada en  {url_file}")

    # ── Mantener proceso vivo ──
    log.info("Sistema activo. Presiona Ctrl+C para detener.")
    try:
        while True:
            time.sleep(10)
            # Verificar que Flask sigue vivo
            if flask_process and flask_process.poll() is not None:
                log.error("Flask se detuvo inesperadamente. Cerrando…")
                cleanup()
    except KeyboardInterrupt:
        cleanup()
