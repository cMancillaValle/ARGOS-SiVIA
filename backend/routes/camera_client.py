"""
routes/camera_client.py (Compatibilidad con FastAPI)
────────────────────────────────────────────────────
Re-exporta los métodos y mapas de la cámara cliente desde api.routers.camera_client
sin ninguna dependencia de Flask.
"""

from api.routers.camera_client import (
    get_client_camera,
    get_client_by_camera,
    remove_client_camera,
    _client_cameras,
)

__all__ = [
    "get_client_camera",
    "get_client_by_camera",
    "remove_client_camera",
    "_client_cameras",
]