"""
ARGOS - SiViA · Deprecated Entrypoint
────────────────────────────────────────────────────────────
app.py ha sido reemplazado por main.py (FastAPI + Uvicorn).
Este script inicia automáticamente main:app para compatibilidad.
"""

import sys
import subprocess

if __name__ == "__main__":
    print("[Aviso] app.py (Flask) ha sido reemplazado por main.py (FastAPI). Iniciando Uvicorn...")
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
    sys.exit(subprocess.call(cmd))