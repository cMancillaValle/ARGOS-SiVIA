#!/usr/bin/env python3
"""
ARGOS - SiViA · Configuración inicial de Ngrok
================================================
Ejecuta este script UNA SOLA VEZ para guardar tu AuthToken.
Uso: python setup_ngrok.py
"""
import os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE, ".ngrok_token")

print("\n" + "═"*52)
print("  ARGOS - SiViA  ·  Configuración Ngrok")
print("═"*52)
print("  Obtén tu token en:")
print("  https://dashboard.ngrok.com/get-started/your-authtoken")
print("═"*52)

if os.path.exists(TOKEN_FILE):
    print("\n  ⚠  Ya existe un token guardado.")
    resp = input("  ¿Sobreescribir? (s/N): ").strip().lower()
    if resp != "s":
        print("  Sin cambios.\n")
        sys.exit(0)

token = input("\n  Pega tu AuthToken aquí: ").strip()
if not token:
    print("  Token vacío. Sin cambios.\n")
    sys.exit(1)

with open(TOKEN_FILE, "w") as f:
    f.write(token)

print(f"\n  ✓  Token guardado en: {TOKEN_FILE}")
print("  ✓  Archivo excluido de git (.gitignore)")
print("\n  Ahora ejecuta: python ngrok_tunnel.py\n")
