import cv2
import os
import time
from datetime import datetime


class CaptureManager:
    """
    Gestiona la captura y almacenamiento de imágenes
    asociadas a eventos detectados por Athena.
    """

    def __init__(self):
        # backend/core_ia/athena/evidence/
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # backend/
        backend_dir = os.path.abspath(
            os.path.join(current_dir, "..", "..", "..")
        )

        # Carpeta donde se almacenarán las evidencias
        self.evidence_dir = os.path.join(
            backend_dir,
            "evidence"
        )

        os.makedirs(self.evidence_dir, exist_ok=True)

    def save_capture(self, frame, event):
        """
        Guarda el frame correspondiente a un evento detectado.

        Parámetros:
            frame: imagen OpenCV (numpy array)
            event: diccionario con información del evento

        Retorna:
            Ruta relativa de la captura o None si ocurre un error.
        """

        if frame is None:
            print("[CAPTURE] Frame vacío. No se puede guardar.")
            return None

        try:
            # Información del evento
            event_type = event.get(
                "tipo",
                "EVENTO"
            )

            subtype = event.get(
                "subtipo",
                "general"
            )

            track_id = event.get(
                "track_id",
                "unknown"
            )

            cam_id = event.get(
                "cam_id",
                "unknown"
            )

            # Fecha y hora
            now = datetime.now()

            date_folder = now.strftime("%Y-%m-%d")

            timestamp = now.strftime(
                "%Y%m%d_%H%M%S_%f"
            )[:-3]

            # Crear carpeta de la cámara
            camera_dir = os.path.join(
                self.evidence_dir,
                f"cam_{cam_id}",
                date_folder
            )

            os.makedirs(
                camera_dir,
                exist_ok=True
            )

            # Limpiar valores para utilizarlos en el nombre
            safe_event = str(event_type).replace(
                " ",
                "_"
            )

            safe_subtype = str(subtype).replace(
                " ",
                "_"
            )

            # Nombre final
            filename = (
                f"{timestamp}_"
                f"{safe_event}_"
                f"{safe_subtype}_"
                f"persona_{track_id}.jpg"
            )

            filepath = os.path.join(
                camera_dir,
                filename
            )

            # Guardar imagen
            success = cv2.imwrite(
                filepath,
                frame
            )

            if not success:
                print(
                    f"[CAPTURE] No se pudo guardar: {filepath}"
                )
                return None

            # Ruta relativa respecto a backend/
            relative_path = os.path.relpath(
                filepath,
                os.path.dirname(self.evidence_dir)
            )

            print(
                f"[CAPTURE] Evidencia guardada: {filepath}"
            )

            return relative_path.replace(
                "\\",
                "/"
            )

        except Exception as e:
            print(
                f"[CAPTURE] Error guardando evidencia: {e}"
            )

            return None


# Instancia global
capture_manager = CaptureManager()