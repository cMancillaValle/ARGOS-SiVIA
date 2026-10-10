#!/usr/bin/env python3
"""
ARGOS - SiViA · Script de inicio rápido (FastAPI + Uvicorn)
============================================================
Ejecuta:   python start.py
Servidor:  http://localhost:5000
"""
import os
import sys
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(BASE, 'backend')
PORT = os.environ.get("ARGOS_PORT", "5000")

# Verificar que FastAPI y Uvicorn estén instalados
try:
    import fastapi
    import uvicorn
except ImportError:
    print("FastAPI o Uvicorn no están instalados. Instalando dependencias...")
    subprocess.check_call([
        sys.executable, '-m', 'pip', 'install', '-r', os.path.join(BACKEND, 'requirements.txt')
    ])

print("\n" + "═"*50)
print("  ARGOS - SiViA · Iniciando servidor FastAPI...")
print("═"*50)
print(f"  Directorio: {BASE}")
print(f"  Backend:    {BACKEND}")
print(f"  Puerto:     {PORT}")
print("═"*50 + "\n")

os.chdir(BACKEND)
cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(PORT), "--workers", "1"]
os.execv(sys.executable, cmd)
