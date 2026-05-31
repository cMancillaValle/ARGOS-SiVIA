"""
core_ia/athena/client_frame_buffer.py
──────────────────────────────────────────────────────────────────────────────
Buffer thread-safe para frames JPEG enviados desde el navegador cliente
(modo cámara remota / webcam del usuario).

El WebSocket de camera_client.py escribe aquí.
El AthenaEngine lee de aquí cuando source == "webcam".
"""

import threading
import time
from typing import Optional


class ClientFrameBuffer:
    """
    Buffer circular de tamaño 1: siempre tiene el frame MÁS RECIENTE.
    Notifica a los consumidores vía threading.Event.
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._frame:  Optional[bytes] = None
        self._ts:     float = 0.0
        self._event   = threading.Event()
        self._active  = False   # True mientras hay un cliente WS conectado
        self._client_id: Optional[str] = None

    # ── Escritura (desde WebSocket handler) ─────────────────────────────────

    def write(self, jpeg_bytes: bytes, client_id: str = ""):
        with self._lock:
            self._frame     = jpeg_bytes
            self._ts        = time.monotonic()
            self._active    = True
            self._client_id = client_id
        self._event.set()

    # ── Lectura (desde AthenaEngine) ─────────────────────────────────────────

    def read(self) -> Optional[bytes]:
        with self._lock:
            return self._frame

    def read_with_ts(self):
        """Retorna (jpeg_bytes, timestamp)."""
        with self._lock:
            return self._frame, self._ts

    def wait_for_new(self, timeout: float = 0.1) -> bool:
        """Bloquea hasta que llegue un frame nuevo (o timeout)."""
        signaled = self._event.wait(timeout=timeout)
        self._event.clear()
        return signaled

    # ── Estado ───────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        with self._lock:
            if not self._active:
                return False
            # Considerar inactivo si hace más de 5s sin frame
            return (time.monotonic() - self._ts) < 5.0

    def disconnect(self):
        with self._lock:
            self._active    = False
            self._client_id = None

    def status(self) -> dict:
        with self._lock:
            age = (time.monotonic() - self._ts) if self._ts else None
            return {
                "active":    self._active,
                "client_id": self._client_id,
                "frame_age": round(age, 2) if age is not None else None,
            }


# ── Instancia global (compartida entre el WS handler y AthenaEngine) ─────────
client_buffer = ClientFrameBuffer()
