"""
core_ia/athena/athena_engine.py
─────────────────────────────────────────────────────────────────────
Motor de Athena IA — integración con vision_env (Python 3.10).

Arquitectura:
  Flask (Python 3.13)                    vision_env (Python 3.10)
  ┌─────────────────────┐  stdout pipe   ┌───────────────────────┐
  │  AthenaThread        │◄──────────────│  athena_worker.py      │
  │  (lee protocolo)     │               │  cv2 / YOLO / MediaPipe│
  │  ┌──────────────┐   │               │  (detección real)      │
  │  │ AthenaBuffer │   │               └───────────────────────┘
  │  │ (JPEG bytes) │   │
  │  └──────────────┘   │
  │  ┌──────────────┐   │
  │  │ event_queue  │   │
  │  └──────────────┘   │
  └─────────────────────┘
       ↓                ↓
  /api/camaras/stream   /api/camaras/eventos/stream
  (MJPEG multipart)     (Server-Sent Events)

Protocolo binario (stdout del worker):
  [1 byte tipo][4 bytes big-endian longitud][payload]
  0x01 → Frame JPEG
  0x02 → Evento JSON UTF-8
  0xFF → Heartbeat (sin payload)
"""

import os
import sys
import time
import struct
import threading
import subprocess
import queue
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Ruta al intérprete del vision_env ────────────────────────────────────────
_ATHENA_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_ATHENA_DIR, '..', '..', '..'))
_VENV_PYTHON  = os.path.join(_PROJECT_ROOT, 'vision_env', 'Scripts', 'python.exe')
_WORKER_SCRIPT = os.path.join(_ATHENA_DIR, 'athena_worker.py')

# ── Catálogo de eventos ───────────────────────────────────────────────────────
EVENTS = {
    "PERSONA_DETECTADA":  "persona",
    "BRAZO_ARRIBA":       "brazo",
    "MANO_ABIERTA":       "mano_abierta",
    "MANO_CERRADA":       "mano_cerrada",
    "TARJETA_VALIDA":     "tarjeta_valida",
    "TARJETA_INVALIDA":   "tarjeta_invalida",
    "ACCESO_CONCEDIDO":   "acceso",
    "POSE_ANOMALA":       "pose_anomala",
    "EVASION_DETECTADA":  "evasion",   # Colados / evasión de pago TransMilenio
}


# ── Buffer thread-safe para el último frame procesado ────────────────────────

class AthenaBuffer:
    def __init__(self):
        self._lock   = threading.Lock()
        self._frame: Optional[bytes] = None
        self._ts: float = 0.0
        self._event  = threading.Event()   # señal: llegó frame nuevo

    def write(self, jpeg_bytes: bytes):
        with self._lock:
            self._frame = jpeg_bytes
            self._ts    = time.monotonic()
        self._event.set()  # despertar a generate_stream()

    def read(self) -> Optional[bytes]:
        with self._lock:
            return self._frame

    def read_with_ts(self):
        """Retorna (jpeg_bytes, timestamp) de forma atómica."""
        with self._lock:
            return self._frame, self._ts

    def wait_for_new(self, timeout: float = 0.05) -> bool:
        """Bloquea hasta que llegue un frame nuevo (o timeout). Retorna True si hay frame."""
        signaled = self._event.wait(timeout=timeout)
        self._event.clear()
        return signaled

    def age(self) -> float:
        with self._lock:
            return time.monotonic() - self._ts if self._ts else 9999.0


# ── Hilo lector del proceso hijo ─────────────────────────────────────────────

class AthenaThread(threading.Thread):
    """
    Lanza `athena_worker.py` con el Python del vision_env y lee
    su protocolo binario desde stdout.
    """

    MSG_FRAME = 0x01
    MSG_EVENT = 0x02
    MSG_HB    = 0xFF

    def __init__(self, cam_id: int, source, buffer: AthenaBuffer,
                 event_queue: queue.Queue, confidence: float = 0.50,
                 mode: str = 'acceso', tripwire: float = 0.55):
        super().__init__(daemon=True, name=f"AthenaThread-cam{cam_id}")
        self.cam_id      = cam_id
        self.source      = source
        self.buffer      = buffer
        self.event_queue = event_queue
        self.confidence  = confidence
        self.mode        = mode
        self.tripwire    = tripwire
        self._stop_ev    = threading.Event()
        self._running    = False
        self._proc: Optional[subprocess.Popen] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def stop(self):
        self._stop_ev.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def _check_venv(self) -> bool:
        if not os.path.isfile(_VENV_PYTHON):
            logger.error(f"vision_env no encontrado: {_VENV_PYTHON}")
            return False
        if not os.path.isfile(_WORKER_SCRIPT):
            logger.error(f"Worker no encontrado: {_WORKER_SCRIPT}")
            return False
        return True

    def _spawn(self) -> Optional[subprocess.Popen]:
        cmd = [
            _VENV_PYTHON, _WORKER_SCRIPT,
            '--source',     str(self.source),
            '--confidence', str(self.confidence),
            '--cam-id',     str(self.cam_id),
            '--mode',       self.mode,
            '--tripwire',   str(self.tripwire),
        ]
        logger.info(f"Lanzando worker: {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,           # unbuffered — crítico para streaming
                cwd=_ATHENA_DIR,     # CWD = athena dir → rutas YOLO relativas funcionan
                close_fds=True,
            )
            threading.Thread(
                target=self._log_stderr,
                args=(proc,),
                daemon=True,
                name=f"AthenaStderr-cam{self.cam_id}",
            ).start()
            return proc
        except Exception as e:
            logger.error(f"No se pudo lanzar worker: {e}")
            return None

    @staticmethod
    def _log_stderr(proc: subprocess.Popen):
        try:
            for line in proc.stderr:
                line = line.decode('utf-8', errors='replace').rstrip()
                if line:
                    logger.error(f"[WORKER IA] {line}")
        except Exception:
            pass

    def _read_exact(self, n: int) -> Optional[bytes]:
        """Lee exactamente n bytes del stdout del proceso hijo."""
        buf = b''
        while len(buf) < n and not self._stop_ev.is_set():
            try:
                chunk = self._proc.stdout.read(n - len(buf))
                if not chunk:
                    return None  # EOF → proceso terminó
                buf += chunk
            except Exception:
                return None
        return buf if len(buf) == n else None

    def run(self):
        self._running = True
        logger.info(f"▶ AthenaThread cam={self.cam_id} source={self.source!r}")

        if not self._check_venv():
            self._emit_error_frame()
            self._running = False
            return

        retry_delay = 3

        while not self._stop_ev.is_set():
            self._proc = self._spawn()
            if not self._proc:
                self._emit_error_frame()
                self._stop_ev.wait(retry_delay)
                continue

            # ── Loop de lectura del protocolo ────────────────────────────
            try:
                while not self._stop_ev.is_set():
                    # Verificar que el proceso sigue vivo
                    if self._proc.poll() is not None:
                        logger.warning(f"Worker terminó (returncode={self._proc.returncode}). Reiniciando...")
                        break

                    # Leer header: 1 byte tipo + 4 bytes longitud
                    header = self._read_exact(5)
                    if header is None:
                        break

                    msg_type   = header[0]
                    payload_len = struct.unpack('>I', header[1:5])[0]

                    if msg_type == self.MSG_HB:
                        continue  # heartbeat, ignorar

                    if payload_len == 0:
                        continue

                    payload = self._read_exact(payload_len)
                    if payload is None:
                        break

                    if msg_type == self.MSG_FRAME:
                        self.buffer.write(payload)

                    elif msg_type == self.MSG_EVENT:
                        try:
                            import json
                            ev = json.loads(payload.decode('utf-8'))
                            self.event_queue.put_nowait(ev)
                        except Exception:
                            pass

            except Exception as e:
                logger.error(f"Error leyendo worker: {e}")
            finally:
                if self._proc and self._proc.poll() is None:
                    self._proc.terminate()

            if not self._stop_ev.is_set():
                logger.info(f"Reintentando en {retry_delay}s...")
                self._stop_ev.wait(retry_delay)

        self._running = False
        logger.info(f"⏹ AthenaThread cam={self.cam_id} detenido")

    def _emit_error_frame(self):
        """Escribe un frame de error en el buffer cuando vision_env no está disponible."""
        try:
            import numpy as np
            import cv2
            h, w = 480, 640
            frame = np.zeros((h, w, 3), dtype='uint8')
            cv2.putText(frame, "ATHENA NO DISPONIBLE", (80, h // 2 - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 180), 2)
            cv2.putText(frame, "vision_env no encontrado", (120, h // 2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (60, 60, 100), 1)
            _, buf = cv2.imencode('.jpg', frame)
            self.buffer.write(buf.tobytes())
        except Exception:
            pass


# ── Manager Singleton ─────────────────────────────────────────────────────────

class AthenaWebcamRelay(threading.Thread):
    """
    Hilo que copia frames del ClientFrameBuffer al AthenaBuffer principal.
    Se usa cuando source == 'webcam': el navegador cliente es la camara.
    """
    def __init__(self, client_buf, athena_buf: AthenaBuffer):
        super().__init__(daemon=True, name='AthenaWebcamRelay')
        self._stop_ev    = threading.Event()
        self._client_buf = client_buf
        self._athena_buf = athena_buf
        self.is_running  = False

    def stop(self):
        self._stop_ev.set()

    def run(self):
        self.is_running = True
        logger.info('AthenaWebcamRelay iniciado')
        last_ts = -1.0
        while not self._stop_ev.is_set():
            self._client_buf.wait_for_new(timeout=0.1)
            frame_bytes, ts = self._client_buf.read_with_ts()
            if frame_bytes and ts != last_ts:
                last_ts = ts
                self._athena_buf.write(frame_bytes)
        self.is_running = False
        logger.info('AthenaWebcamRelay detenido')


class AthenaManager:
    """
    Gestiona el ciclo de vida del AthenaThread activo (o AthenaWebcamRelay).
    Unico en el proceso Flask.
    """

    def __init__(self):
        self._lock           = threading.Lock()
        self._thread         = None
        self._relay          = None
        self.buffer          = AthenaBuffer()
        self.event_queue     = queue.Queue(maxsize=200)
        self._active_cam_id  = None
        self._webcam_mode    = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            if self._webcam_mode:
                return self._relay is not None and self._relay.is_running
            return self._thread is not None and self._thread.is_running

    @property
    def active_cam_id(self):
        return self._active_cam_id

    def _get_client_buf(self):
        try:
            athena_dir = os.path.dirname(os.path.abspath(__file__))
            if athena_dir not in sys.path:
                sys.path.insert(0, athena_dir)
            from client_frame_buffer import client_buffer
            return client_buffer
        except Exception as e:
            logger.error(f'No se pudo importar client_frame_buffer: {e}')
            return None

    def start(self, cam_id: int, source, confidence: float = 0.50,
              mode: str = 'acceso', tripwire: float = 0.55):
        with self._lock:
            # Detener lo que este corriendo
            if self._thread and self._thread.is_running:
                logger.info(f'Deteniendo hilo anterior cam={self._active_cam_id}')
                self._thread.stop()
                self._thread.join(timeout=6)
                self._thread = None
            if self._relay and self._relay.is_running:
                self._relay.stop()
                self._relay.join(timeout=3)
                self._relay = None

            # Vaciar cola de eventos
            while not self.event_queue.empty():
                try:
                    self.event_queue.get_nowait()
                except queue.Empty:
                    break

            self._active_cam_id = cam_id
            self._webcam_mode = (str(source).strip().lower() == 'webcam')
            self._mode = mode

            # Si es webcam, usar el endpoint MJPEG local interno como fuente de OpenCV
            engine_source = 'http://127.0.0.1:5000/api/camaras/client/mjpeg' if self._webcam_mode else source

            # Iniciar siempre el worker de IA en subprocess
            self._thread = AthenaThread(
                cam_id=cam_id,
                source=engine_source,
                buffer=self.buffer,
                event_queue=self.event_queue,
                confidence=confidence,
                mode=mode,
                tripwire=tripwire,
            )
            self._thread.start()
            logger.info(f'Athena iniciado cam={cam_id} source={source!r} mode={mode}')

    def stop(self):
        with self._lock:
            if self._thread and self._thread.is_running:
                self._thread.stop()
                self._thread.join(timeout=6)
                self._thread = None
            if self._relay and self._relay.is_running:
                self._relay.stop()
                self._relay.join(timeout=3)
                self._relay = None
            self._active_cam_id = None
            self._webcam_mode   = False
            self._mode          = 'acceso'
            logger.info('Athena detenido')

    def status(self) -> dict:
        return {
            'running':      self.is_running,
            'cam_id':       self._active_cam_id,
            'webcam_mode':  self._webcam_mode,
            'mode':         getattr(self, '_mode', 'acceso'),
            'venv_ok':      os.path.isfile(_VENV_PYTHON),
            'venv_path':    _VENV_PYTHON,
        }

    def generate_stream(self):
        """
        Generador MJPEG para Flask Response.
        Usa threading.Event: envia el frame TAN PRONTO como llega del worker,
        sin sleep fijo. Nunca envia el mismo frame dos veces.
        """
        boundary = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
        last_ts = -1.0
        while True:
            self.buffer.wait_for_new(timeout=0.05)
            frame_bytes, ts = self.buffer.read_with_ts()
            if frame_bytes and ts != last_ts:
                last_ts = ts
                yield boundary + frame_bytes + b'\r\n'


# -- Instancia global
athena = AthenaManager()
