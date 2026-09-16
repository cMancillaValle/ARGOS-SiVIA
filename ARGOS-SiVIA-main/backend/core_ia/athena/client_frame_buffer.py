import threading
import time


class ClientFrameBuffer:
    def __init__(self):
        self._frames = {}
        self._lock = threading.Lock()

    def write(self, jpeg_bytes, client_id):
        with self._lock:
            self._frames[client_id] = {
                "frame": jpeg_bytes,
                "ts": time.time()
            }

    def read(self, client_id):
        with self._lock:
            data = self._frames.get(client_id)

            if not data:
                return None

            return data["frame"]

    def remove(self, client_id):
        with self._lock:
            self._frames.pop(client_id, None)

    def clients(self):
        with self._lock:
            return list(self._frames.keys())


client_buffer = ClientFrameBuffer()