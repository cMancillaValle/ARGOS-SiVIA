"""
backend/fastapi_poc/app.py
──────────────────────────────────────────────────────────────────────────────
Módulo de prueba / Compatibilidad PoC.

El WebSocket de ingesta de cámaras ha sido promovido e integrado completamente
en la aplicación principal de producción de ARGOS-SiViA:
    backend/main.py
    backend/api/routers/camera_client.py

Este módulo re-exporta la aplicación oficial para pruebas automatizadas y
mantiene compatibilidad con scripts de benchmarking aislados.
"""

from main import app, get_client_camera, get_client_by_camera, remove_client_camera, _client_cameras

__all__ = [
    "app",
    "get_client_camera",
    "get_client_by_camera",
    "remove_client_camera",
    "_client_cameras",
]
