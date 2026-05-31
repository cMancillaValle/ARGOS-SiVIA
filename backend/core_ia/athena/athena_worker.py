"""
core_ia/athena/athena_worker.py
─────────────────────────────────────────────────────────────────────
Script diseñado para correr DENTRO del entorno vision_env (Python 3.10)
NUNCA importar desde Flask/Python 3.13 directamente.

Protocolo de salida (stdout binario, length-prefixed):
  [1 byte tipo] [4 bytes longitud big-endian] [payload]
  - Tipo 0x01: Frame JPEG
  - Tipo 0x02: Evento JSON (UTF-8)
  - Tipo 0xFF: Heartbeat (sin payload, longitud=0)

Argumentos CLI:
  --source <int_o_url>   Fuente de video (0 = cámara local, rtsp://... = IP)
  --confidence <float>   Umbral de confianza (default: 0.50)
  --model <str>          Modelo YOLO (default: yolov8n.pt)
"""

import sys
import os
import json
import time
import struct
import argparse
import logging
import traceback

# ── Configurar logging a stderr (stdout reservado para frames/eventos) ────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='[WORKER %(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ── Path setup para detectores locales ───────────────────────────────────────
WORKER_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKER_DIR not in sys.path:
    sys.path.insert(0, WORKER_DIR)


# ── Helpers de protocolo binario ─────────────────────────────────────────────

def write_msg(msg_type: int, payload: bytes):
    """Escribe un mensaje en stdout binario (thread-unsafe, llamar desde un solo hilo)."""
    header = struct.pack('>BI', msg_type, len(payload))
    try:
        sys.stdout.buffer.write(header + payload)
        sys.stdout.buffer.flush()
    except (BrokenPipeError, OSError):
        sys.exit(0)  # Padre cerró la conexión


def send_frame(jpeg_bytes: bytes):
    write_msg(0x01, jpeg_bytes)


def send_event(evento: dict):
    write_msg(0x02, json.dumps(evento, ensure_ascii=False).encode('utf-8'))


def send_heartbeat():
    write_msg(0xFF, b'')


# ── Importaciones IA ──────────────────────────────────────────────────────────

def load_imports():
    """Carga las librerías de IA con mensajes de error informativos."""
    mods = {}

    try:
        import cv2
        mods['cv2'] = cv2
        logger.info(f"cv2 {cv2.__version__} cargado")
    except ImportError as e:
        logger.critical(f"cv2 no disponible: {e}")
        sys.exit(1)

    try:
        import numpy as np
        mods['np'] = np
    except ImportError as e:
        logger.critical(f"numpy no disponible: {e}")
        sys.exit(1)

    # Detectores opcionales (si fallan, el worker sigue sin esa detección)
    try:
        from detectors.person_detector import detectar_persona
        mods['detectar_persona'] = detectar_persona
        logger.info("Detector persona cargado")
    except Exception as e:
        logger.warning(f"Detector persona no disponible: {e}")

    try:
        from detectors.pose_detector import detectar_brazo
        mods['detectar_brazo'] = detectar_brazo
        logger.info("Detector pose cargado")
    except Exception as e:
        logger.warning(f"Detector pose no disponible: {e}")

    try:
        from detectors.hand_detector import detectar_mano
        mods['detectar_mano'] = detectar_mano
        logger.info("Detector manos cargado")
    except Exception as e:
        logger.warning(f"Detector manos no disponible: {e}")

    try:
        from detectors.face_detector import detectar_rostro
        mods['detectar_rostro'] = detectar_rostro
        logger.info("Detector rostro (FaceMesh) cargado")
    except Exception as e:
        logger.warning(f"Detector rostro no disponible: {e}")

    try:
        from detectors.card_detector import detectar_tarjeta
        mods['detectar_tarjeta'] = detectar_tarjeta
        logger.info("Detector tarjeta cargado")
    except Exception as e:
        logger.warning(f"Detector tarjeta no disponible: {e}")

    return mods


# ── Frame placeholder ─────────────────────────────────────────────────────────

def placeholder_frame(np, cv2, source) -> bytes:
    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype='uint8')
    ts = time.strftime('%H:%M:%S')
    cv2.putText(frame, "SIN SENAL", (w // 2 - 100, h // 2 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (50, 50, 50), 2)
    cv2.putText(frame, f"Fuente: {str(source)[:40]}", (20, h - 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1)
    cv2.putText(frame, ts, (20, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 40), 1)
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return buf.tobytes()


# ── Overlay HUD ───────────────────────────────────────────────────────────────

def draw_overlay(cv2, frame, estado: dict, cam_source):
    h, w = frame.shape[:2]
    ts = time.strftime('%H:%M:%S')
    cv2.putText(frame, f"{ts}  SRC:{str(cam_source)[:20]}", (10, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    mano_txt = estado.get("mano", "") or "-"
    labels = [
        ("PERSONA", estado.get("persona", False), (0, 200, 255)),
        ("ROSTRO",  estado.get("rostro",  False), (80, 200, 80)),
        ("BRAZO",   estado.get("brazo",   False), (255, 165, 0)),
        (f"MANO:{mano_txt.upper()}", mano_txt not in ("", "-"), (200, 80, 255)),
        ("TARJETA", estado.get("tarjeta", False), (0, 255, 100)),
    ]
    for i, (lbl, activo, color) in enumerate(labels):
        clr = color if activo else (45, 45, 45)
        cv2.putText(frame, f"[{lbl}]" if activo else lbl,
                    (10, h - 20 - i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, clr, 1, cv2.LINE_AA)



# ── Detección de eventos (edge-detection) ─────────────────────────────────────

class EdgeDetector:
    def __init__(self, cooldown: float = 3.0):
        self.prev = {"persona": False, "brazo": False, "mano": "", "tarjeta": False}
        self.last_acceso = 0.0
        self.cooldown = cooldown

    def process(self, estado: dict, cam_id: int) -> list:
        eventos = []
        now = time.time()
        p = self.prev

        if estado["persona"] and not p["persona"]:
            eventos.append({"tipo": "PERSONA_DETECTADA", "descripcion": "Persona detectada", "cam_id": cam_id, "ts": now})

        if estado["brazo"] and not p["brazo"]:
            eventos.append({"tipo": "BRAZO_ARRIBA", "descripcion": "Brazo levantado", "cam_id": cam_id, "ts": now})

        if estado["mano"] and estado["mano"] != p["mano"]:
            if estado["mano"] == "abierta":
                eventos.append({"tipo": "MANO_ABIERTA", "descripcion": "Mano abierta detectada", "cam_id": cam_id, "ts": now})
            elif estado["mano"] == "cerrada":
                eventos.append({"tipo": "MANO_CERRADA", "descripcion": "Mano cerrada detectada", "cam_id": cam_id, "ts": now})

        if estado["tarjeta"] and not p["tarjeta"]:
            eventos.append({"tipo": "TARJETA_VALIDA", "descripcion": "Tarjeta válida detectada", "cam_id": cam_id, "ts": now})

        if (estado["persona"] and estado["brazo"] and
                estado["mano"] == "abierta" and estado["tarjeta"]):
            if now - self.last_acceso > self.cooldown:
                self.last_acceso = now
                eventos.append({"tipo": "ACCESO_CONCEDIDO", "descripcion": "Acceso biométrico concedido", "cam_id": cam_id, "ts": now})

        self.prev = dict(estado)
        return eventos


# ── Lector de Cámara Sin Retraso (Multithreading) ─────────────────────────────
import threading

class FastCameraReader:
    def __init__(self, cv2, source):
        self.cv2 = cv2
        self.source = source
        # Establecer env vars ANTES de abrir VideoCapture para RTSP de baja latencia
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|fflags;nobuffer|flags;low_delay'

        self.cap = cv2.VideoCapture(source)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.ret = False
        self.frame = None
        self.running = True
        self.lock = threading.Lock()

        if self.cap.isOpened():
            self.thread = threading.Thread(target=self._update, daemon=True)
            self.thread.start()

    def _update(self):
        """Hilo dedicado: lee frames a máxima velocidad para siempre tener el más reciente."""
        consecutive_failures = 0
        while self.running:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    consecutive_failures = 0
                    with self.lock:
                        self.ret = True
                        self.frame = frame
                else:
                    consecutive_failures += 1
                    if consecutive_failures > 10:
                        # Cap realmente muerta, marcar como fallida
                        with self.lock:
                            self.ret = False
                        time.sleep(0.1)
            else:
                time.sleep(0.05)

    def isOpened(self):
        return self.cap.isOpened()

    def read(self):
        with self.lock:
            if self.frame is not None:
                return self.ret, self.frame.copy()
            # Aún no llegó el primer frame — no es error fatal
            return True, None

    def release(self):
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2.0)
        self.cap.release()


# ── Loop Principal ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Athena IA Worker')
    parser.add_argument('--source',     default='0',    help='Video source (int index or RTSP URL)')
    parser.add_argument('--confidence', type=float, default=0.50, help='Detection confidence threshold')
    parser.add_argument('--cam-id',     type=int,   default=0,    help='Camera ID for events')
    parser.add_argument('--model',      default='yolov8n.pt',     help='YOLO model filename')
    args = parser.parse_args()

    # Resolver fuente
    source = int(args.source) if args.source.isdigit() else args.source
    cam_id = args.cam_id

    logger.info(f"Worker iniciado: source={source} cam_id={cam_id} confidence={args.confidence}")

    # Cargar librerías
    mods = load_imports()
    cv2 = mods['cv2']
    np  = mods['np']

    edge = EdgeDetector()
    cap  = None
    retry_delay = 2.0
    hb_interval = 10.0
    last_hb     = time.time()
    frame_interval = 1.0 / 30  # usado solo en caso futuro
    last_frame_ts  = 0.0

    while True:
        # ── Conectar/Reconectar ───────────────────────────────────────────
        if cap is None or not cap.isOpened():
            logger.info(f"Conectando a: {source}")
            cap = FastCameraReader(cv2, source)
            if not cap.isOpened():
                logger.warning(f"No se pudo abrir fuente {source!r}. Reintento en {retry_delay}s")
                send_frame(placeholder_frame(np, cv2, source))
                time.sleep(retry_delay)
                cap.release()
                cap = None
                continue
            logger.info("Fuente abierta OK")

        # ── Heartbeat ─────────────────────────────────────────────────────
        now = time.time()
        if now - last_hb >= hb_interval:
            send_heartbeat()
            last_hb = now

        # ── Leer frame ────────────────────────────────────────────────────
        ret, frame = cap.read()

        # frame==None significa que el hilo aún no capturó el primer frame: esperar sin reconectar
        if frame is None:
            time.sleep(0.01)
            continue

        # ret==False con frame conocido significa cap realmente muerta
        if not ret:
            logger.warning("Fuente perdida — reconectando")
            cap.release()
            cap = None
            send_frame(placeholder_frame(np, cv2, source))
            time.sleep(retry_delay)
            continue

        # ── Preprocesamiento ──────────────────────────────────────────────
        # Escalar a 640px: menor área = inferencia YOLO/MediaPipe más rápida
        h, w = frame.shape[:2]
        if w > 640:
            scale = 640 / w
            frame = cv2.resize(frame, (640, int(h * scale)), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # ── Detección ─────────────────────────────────────────────────────
        estado = {"persona": False, "brazo": False, "mano": "", "tarjeta": False, "rostro": False}

        if 'detectar_persona' in mods:
            try:
                estado["persona"], frame = mods['detectar_persona'](frame)
            except Exception as e:
                logger.debug(f"persona: {e}")

        if 'detectar_rostro' in mods:
            try:
                estado["rostro"], frame = mods['detectar_rostro'](frame, rgb)
            except Exception as e:
                logger.debug(f"rostro: {e}")

        if 'detectar_brazo' in mods:
            try:
                estado["brazo"], frame = mods['detectar_brazo'](frame, rgb)
            except Exception as e:
                logger.debug(f"brazo: {e}")

        if 'detectar_mano' in mods:
            try:
                estado["mano"], frame = mods['detectar_mano'](frame, rgb)
            except Exception as e:
                logger.debug(f"mano: {e}")

        if 'detectar_tarjeta' in mods:
            try:
                estado["tarjeta"], frame = mods['detectar_tarjeta'](frame)
            except Exception as e:
                logger.debug(f"tarjeta: {e}")

        # ── Overlay HUD ───────────────────────────────────────────────────
        draw_overlay(cv2, frame, estado, source)

        # ── Enviar Frame ──────────────────────────────────────────────────
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            send_frame(buf.tobytes())

        # ── Enviar Eventos ────────────────────────────────────────────────
        for ev in edge.process(estado, cam_id):
            send_event(ev)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Worker detenido por señal")
    except Exception as e:
        logger.critical(f"Error fatal: {e}\n{traceback.format_exc()}")
        sys.exit(1)
