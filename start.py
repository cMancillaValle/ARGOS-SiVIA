#!/usr/bin/env python3
"""
ARGOS - SiViA · Script de inicio rápido
========================================
Ejecuta:   python start.py
Servidor:  http://localhost:5000
"""
import os, sys, subprocess

BASE  = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(BASE, 'backend')
APP     = os.path.join(BACKEND, 'app.py')

# Verify Flask is installed
try:
    import flask
except ImportError:
    print("Flask no está instalado. Instalando...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'flask'])

print("\n" + "═"*50)
print("  ARGOS - SiViA · Iniciando sistema...")
print("═"*50)
print(f"  Directorio: {BASE}")
print(f"  Backend:    {APP}")
print("═"*50 + "\n")

os.chdir(BACKEND)
os.execv(sys.executable, [sys.executable, APP])
