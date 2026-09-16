import threading


class CameraManager:
    def __init__(self):
        self.cameras = {}
        self.lock = threading.Lock()

    def add(self, cam_id, athena):
        with self.lock:
            self.cameras[cam_id] = athena

    def get(self, cam_id):
        with self.lock:
            return self.cameras.get(cam_id)

    def remove(self, cam_id):
        with self.lock:
            return self.cameras.pop(cam_id, None)

    def all(self):
        with self.lock:
            return dict(self.cameras)


camera_manager = CameraManager()