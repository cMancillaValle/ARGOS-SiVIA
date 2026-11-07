"""
core_ia/athena/athena_engine.py
─────────────────────────────────────────────────────────────────────
Motor de Athena IA — gestión independiente de múltiples cámaras.

Arquitectura:

    Flask
      │
      ├── AthenaManager
      │      ├── cam 1 → AthenaThread → AthenaBuffer
      │      ├── cam 2 → AthenaThread → AthenaBuffer
      │      └── cam 3 → AthenaThread → AthenaBuffer
      │
      └── athena_worker.py
              │
              ├── OpenCV
              ├── YOLO
              ├── ByteTrack
              └── MediaPipe

Cada cámara posee:
    - Su propio AthenaThread
    - Su propio AthenaBuffer
    - Su propio proceso athena_worker.py

Para webcam:
    browser
        ↓
    WebSocket /client/push
        ↓
    client_frame_buffer
        ↓
    /client/mjpeg?client_id=XXXX
        ↓
    AthenaThread
        ↓
    AthenaBuffer
        ↓
    /api/camaras/<cam_id>/stream

Protocolo binario del worker:

    [1 byte tipo][4 bytes big-endian longitud][payload]

    0x01 → Frame JPEG
    0x02 → Evento JSON UTF-8
    0xFF → Heartbeat
"""

import os
import time
import struct
import threading
import subprocess
import queue
import logging
import json
import uuid
import copy
from typing import Optional, Callable, Any
from urllib.parse import quote

from .camera_manager import camera_manager


logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# RUTAS
# ═════════════════════════════════════════════════════════════════════

_ATHENA_DIR = os.path.dirname(os.path.abspath(__file__))

_PROJECT_ROOT = os.path.normpath(
    os.path.join(_ATHENA_DIR, "..", "..", "..")
)

_VENV_PYTHON = os.path.join(
    _PROJECT_ROOT,
    "vision_env",
    "Scripts",
    "python.exe"
)

_WORKER_SCRIPT = os.path.join(
    _ATHENA_DIR,
    "athena_worker.py"
)


# ═════════════════════════════════════════════════════════════════════
# CATÁLOGO DE EVENTOS
# ═════════════════════════════════════════════════════════════════════

EVENTS = {
    "PERSONA_DETECTADA": "persona",
    "BRAZO_ARRIBA": "brazo",
    "MANO_ABIERTA": "mano_abierta",
    "MANO_CERRADA": "mano_cerrada",
    "TARJETA_VALIDA": "tarjeta_valida",
    "TARJETA_INVALIDA": "tarjeta_invalida",
    "ACCESO_CONCEDIDO": "acceso",
    "POSE_ANOMALA": "pose_anomala",
    "EVASION_DETECTADA": "evasion",
}


# ═════════════════════════════════════════════════════════════════════
# BUFFER DE ATHENA
# ═════════════════════════════════════════════════════════════════════

class AthenaBuffer:
    """
    Guarda el último frame procesado por una cámara.

    Cada AthenaThread posee su propio AthenaBuffer.
    """

    def __init__(self):
        self._lock = threading.Lock()

        self._frame: Optional[bytes] = None
        self._ts: float = 0.0

        # Se activa cuando llega un frame nuevo.
        self._event = threading.Event()

    def write(self, jpeg_bytes: bytes):
        """
        Guarda un nuevo frame JPEG.
        """
        if not jpeg_bytes:
            return

        with self._lock:
            self._frame = jpeg_bytes
            self._ts = time.monotonic()

        self._event.set()

    def read(self) -> Optional[bytes]:
        """
        Retorna el último frame.
        """
        with self._lock:
            return self._frame

    def read_with_ts(self):
        """
        Retorna:

            (frame, timestamp)

        de forma atómica.
        """
        with self._lock:
            return self._frame, self._ts

    def wait_for_new(self, timeout: float = 0.05) -> bool:
        """
        Espera hasta que llegue un nuevo frame.
        """
        signaled = self._event.wait(timeout=timeout)
        self._event.clear()

        return signaled

    def age(self) -> float:
        """
        Retorna la antigüedad del último frame.
        """
        with self._lock:
            if not self._ts:
                return 9999.0

            return time.monotonic() - self._ts

    def clear(self):
        """
        Limpia el buffer.
        """
        with self._lock:
            self._frame = None
            self._ts = 0.0

        self._event.clear()


# ═════════════════════════════════════════════════════════════════════
# HILO DE ATHENA
# ═════════════════════════════════════════════════════════════════════

class AthenaThread(threading.Thread):
    """
    Ejecuta athena_worker.py para UNA cámara.

    Cada cámara tiene su propio proceso de IA.
    """

    MSG_FRAME = 0x01
    MSG_EVENT = 0x02
    MSG_METRICS = 0x03
    MSG_HB = 0xFF

    def __init__(
        self,
        cam_id: int,
        source,
        buffer: AthenaBuffer,
        event_queue: queue.Queue,
        confidence: float = 0.50,
        mode: str = "acceso",
        tripwire: float = 0.55,
        client_id: Optional[str] = None,
        diagnostics: Optional[dict] = None,
        diag_lock: Optional[Any] = None,
        on_session_end: Optional[Callable] = None,
    ):
        super().__init__(
            daemon=True,
            name=f"AthenaThread-cam{cam_id}"
        )

        self.cam_id = cam_id
        self.source = source
        self.buffer = buffer
        self.event_queue = event_queue

        self.confidence = confidence
        self.mode = mode
        self.tripwire = tripwire

        # Solo se utiliza cuando la cámara es una webcam.
        self.client_id = client_id
        self.diagnostics = diagnostics if diagnostics is not None else {}
        self.session_id = str(self.diagnostics.get("session_id", ""))
        self._diag_lock = diag_lock if diag_lock is not None else threading.Lock()
        self._on_session_end = on_session_end

        self._stop_ev = threading.Event()
        self._running = False

        self._proc: Optional[subprocess.Popen] = None

    # ─────────────────────────────────────────────────────────────────
    # ESTADO
    # ─────────────────────────────────────────────────────────────────

    def record_milestone(self, name: str, val: Optional[float] = None):
        """Registra un hito de tiempo relativo al inicio de la sesión de forma sincronizada."""
        with self._diag_lock:
            ms = self.diagnostics.setdefault("milestones_s", {})
            if name not in ms:
                started_at = self.diagnostics.get("started_at", time.perf_counter())
                ms[name] = val if val is not None else (time.perf_counter() - started_at)

    def update_worker_metrics(self, report: dict):
        """Actualiza el último reporte de métricas del worker de forma sincronizada."""
        with self._diag_lock:
            self.diagnostics["worker"] = report
            self.diagnostics["last_report_at"] = time.time()

    def _finalize_session(self):
        """Finaliza la sesión diagnóstica de forma segura e idempotente al terminar el hilo."""
        if self._on_session_end:
            try:
                self._on_session_end(self.cam_id, self.session_id, self.diagnostics)
            except Exception as e:
                logger.warning(
                    f"Error finalizando sesión diagnóstica cam={self.cam_id}: {e}"
                )
        else:
            with self._diag_lock:
                if self.diagnostics and self.diagnostics.get("is_active"):
                    self.diagnostics["ended_at"] = time.time()
                    started_at = self.diagnostics.get("started_at", time.perf_counter())
                    self.diagnostics["duration_s"] = max(0.0, time.perf_counter() - started_at)
                    self.diagnostics["is_active"] = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ─────────────────────────────────────────────────────────────────
    # DETENER
    # ─────────────────────────────────────────────────────────────────

    def stop(self):
        """
        Detiene el thread y su proceso de IA.
        """
        logger.info(
            f"Deteniendo AthenaThread cam={self.cam_id}"
        )

        self._stop_ev.set()

        proc = self._proc

        if proc and proc.poll() is None:
            try:
                proc.terminate()

                proc.wait(timeout=3)

            except Exception:

                try:
                    proc.kill()

                except Exception:
                    pass

        self._running = False

    # ─────────────────────────────────────────────────────────────────
    # VALIDAR ENTORNO
    # ─────────────────────────────────────────────────────────────────

    def _check_venv(self) -> bool:

        if not os.path.isfile(_VENV_PYTHON):

            logger.error(
                f"vision_env no encontrado: {_VENV_PYTHON}"
            )

            return False

        if not os.path.isfile(_WORKER_SCRIPT):

            logger.error(
                f"Worker no encontrado: {_WORKER_SCRIPT}"
            )

            return False

        return True

    # ─────────────────────────────────────────────────────────────────
    # CREAR PROCESO WORKER
    # ─────────────────────────────────────────────────────────────────

    def _spawn(self) -> Optional[subprocess.Popen]:

        cmd = [
            _VENV_PYTHON,
            _WORKER_SCRIPT,

            "--source",
            str(self.source),

            "--confidence",
            str(self.confidence),

            "--cam-id",
            str(self.cam_id),

            "--mode",
            self.mode,

            "--tripwire",
            str(self.tripwire),

            "--session-id",
            str(self.diagnostics.get("session_id", "")),
        ]

        logger.info(
            f"Lanzando worker cam={self.cam_id}: "
            f"{' '.join(cmd)}"
        )

        try:

            self.record_milestone("process_spawn_started_s")

            proc = subprocess.Popen(
                cmd,

                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,

                # Importante para streaming.
                bufsize=0,

                cwd=_ATHENA_DIR,

                close_fds=True,
            )

            threading.Thread(
                target=self._log_stderr,
                args=(proc,),
                daemon=True,
                name=f"AthenaStderr-cam{self.cam_id}",
            ).start()

            self.record_milestone("process_spawned_s")

            return proc

        except Exception as e:

            logger.error(
                f"No se pudo lanzar worker "
                f"cam={self.cam_id}: {e}"
            )

            return None

    # ─────────────────────────────────────────────────────────────────
    # LOG DEL WORKER
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _log_stderr(proc: subprocess.Popen):

        try:

            if proc.stderr is None:
                return

            for line in proc.stderr:

                line = line.decode(
                    "utf-8",
                    errors="replace"
                ).rstrip()

                if line:

                    logger.error(
                        f"[WORKER IA] {line}"
                    )

        except Exception:
            pass

    @staticmethod
    def _persistir_evento_db(ev: dict, cam_id: int):
        """
        Persiste el evento detectado por Athena en la base de datos argos.db.
        """
        try:
            import sqlite3
            db_path = os.path.normpath(
                os.path.join(_PROJECT_ROOT, "database", "argos.db")
            )
            if not os.path.isfile(db_path):
                return

            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute('PRAGMA foreign_keys = ON')
            tipo_raw = str(ev.get("tipo", "evasion")).lower()

            if "evasion" in tipo_raw:
                tipo_db = "evasion"
            elif "intrusion" in tipo_raw:
                tipo_db = "intrusion"
            elif "caida" in tipo_raw:
                tipo_db = "caida"
            else:
                tipo_db = "otro"

            try:
                confianza = float(ev.get("confianza", ev.get("confidence", 0.95)))
            except (ValueError, TypeError):
                confianza = 0.95

            observaciones = ev.get("descripcion", ev.get("mensaje", ""))
            evidencia = ev.get("evidencia", None)

            conn.execute(
                """
                INSERT INTO eventos (camara_id, tipo, confianza, estado, observaciones, evidencia)
                VALUES (?, ?, ?, 'pendiente', ?, ?)
                """,
                (int(cam_id), tipo_db, confianza, observaciones, evidencia)
            )
            conn.commit()
            conn.close()
            logger.info(
                f"[Athena DB] Evento persistido para cámara {cam_id} "
                f"(tipo={tipo_db}, evidencia={evidencia})"
            )
        except Exception as e:
            logger.warning(
                f"[Athena DB] No se pudo guardar evento en BD: {e}"
            )

    # ─────────────────────────────────────────────────────────────────
    # LECTURA EXACTA DEL PIPE
    # ─────────────────────────────────────────────────────────────────

    def _read_exact(self, n: int) -> Optional[bytes]:

        if not self._proc or not self._proc.stdout:
            return None

        buf = b""

        while (
            len(buf) < n
            and not self._stop_ev.is_set()
        ):

            try:

                chunk = self._proc.stdout.read(
                    n - len(buf)
                )

                if not chunk:

                    return None

                buf += chunk

            except Exception:

                return None

        if len(buf) == n:
            return buf

        return None

    # ─────────────────────────────────────────────────────────────────
    # LOOP PRINCIPAL
    # ─────────────────────────────────────────────────────────────────

    def run(self):

        self._running = True
        self.record_milestone("athena_thread_started_s")

        logger.info(
            f"▶ AthenaThread iniciado "
            f"cam={self.cam_id} "
            f"source={self.source!r} "
            f"mode={self.mode} "
            f"client_id={self.client_id}"
        )

        try:
            # -------------------------------------------------------------
            # Verificar entorno
            # -------------------------------------------------------------

            if not self._check_venv():

                self._emit_error_frame()

                return

            retry_delay = 3

            # -------------------------------------------------------------
            # Reinicio automático del worker
            # -------------------------------------------------------------

            while not self._stop_ev.is_set():

                self._proc = self._spawn()

                if not self._proc:

                    self._emit_error_frame()

                    self._stop_ev.wait(
                        retry_delay
                    )

                    continue

                # ---------------------------------------------------------
                # Leer protocolo binario
                # ---------------------------------------------------------

                try:

                    while not self._stop_ev.is_set():

                        # Si el proceso murió.
                        if self._proc.poll() is not None:

                            logger.warning(
                                f"Worker cam={self.cam_id} "
                                f"terminó "
                                f"(returncode="
                                f"{self._proc.returncode}). "
                                f"Reiniciando..."
                            )

                            break

                        # -------------------------------------------------
                        # Header:
                        #
                        # 1 byte  = tipo
                        # 4 bytes = longitud
                        # -------------------------------------------------

                        header = self._read_exact(5)

                        if header is None:
                            break

                        msg_type = header[0]

                        payload_len = struct.unpack(
                            ">I",
                            header[1:5]
                        )[0]

                        # -------------------------------------------------
                        # Heartbeat
                        # -------------------------------------------------

                        if msg_type == self.MSG_HB:

                            continue

                        # -------------------------------------------------
                        # Mensaje sin payload
                        # -------------------------------------------------

                        if payload_len == 0:

                            continue

                        # -------------------------------------------------
                        # Leer payload
                        # -------------------------------------------------

                        payload = self._read_exact(
                            payload_len
                        )

                        if payload is None:

                            break

                        # =================================================
                        # FRAME
                        # =================================================

                        if msg_type == self.MSG_FRAME:

                            self.buffer.write(
                                payload
                            )
                            self.record_milestone("first_jpeg_received_buffer_s")

                        elif msg_type == self.MSG_METRICS:

                            try:
                                report = json.loads(payload.decode("utf-8"))
                                if isinstance(report, dict):
                                    self.update_worker_metrics(report)
                            except Exception as e:
                                logger.warning(f"Diagnóstico inválido de worker cam={self.cam_id}: {e}")

                        # =================================================
                        # EVENTO
                        # =================================================

                        elif msg_type == self.MSG_EVENT:

                            try:

                                ev = json.loads(
                                    payload.decode(
                                        "utf-8"
                                    )
                                )

                                # ------------------------------------------------
                                # Asegurar que el evento tenga cam_id.
                                # ------------------------------------------------

                                if isinstance(ev, dict):

                                    ev.setdefault(
                                        "cam_id",
                                        self.cam_id
                                    )

                                # ------------------------------------------------
                                # Añadir a cola global.
                                #
                                # La cola sigue siendo global, pero cada
                                # evento contiene cam_id, por lo que el
                                # frontend puede saber de qué cámara viene.
                                # ------------------------------------------------

                                try:

                                    self.event_queue.put_nowait(
                                        ev
                                    )

                                except queue.Full:

                                    # Evitar que un exceso de eventos
                                    # bloquee Athena.
                                    logger.warning(
                                        "Cola de eventos llena; "
                                        f"evento descartado "
                                        f"cam={self.cam_id}"
                                    )

                                # Persistir evento en base de datos en segundo plano
                                threading.Thread(
                                    target=self._persistir_evento_db,
                                    args=(ev, self.cam_id),
                                    daemon=True
                                ).start()

                            except Exception as e:

                                logger.error(
                                    f"Error procesando evento "
                                    f"cam={self.cam_id}: {e}"
                                )

                except Exception as e:

                    logger.error(
                        f"Error leyendo worker "
                        f"cam={self.cam_id}: {e}"
                    )

                finally:

                    # -----------------------------------------------------
                    # Cerrar proceso si sigue vivo.
                    # -----------------------------------------------------

                    if (
                        self._proc
                        and self._proc.poll() is None
                    ):

                        try:

                            self._proc.terminate()

                        except Exception:
                            pass

                # ---------------------------------------------------------
                # Reiniciar si no fue detenido manualmente.
                # ---------------------------------------------------------

                if not self._stop_ev.is_set():

                    logger.info(
                        f"Athena cam={self.cam_id} "
                        f"reintentará en "
                        f"{retry_delay}s..."
                    )

                    self._stop_ev.wait(
                        retry_delay
                    )

        except Exception as e:
            logger.error(
                f"Error fatal no controlado en AthenaThread cam={self.cam_id}: {e}",
                exc_info=True
            )

        finally:
            self._running = False
            self._finalize_session()
            logger.info(
                f"⏹ AthenaThread cam={self.cam_id} detenido"
            )

    # ─────────────────────────────────────────────────────────────────
    # FRAME DE ERROR
    # ─────────────────────────────────────────────────────────────────

    def _emit_error_frame(self):

        try:

            import numpy as np
            import cv2

            h, w = 480, 640

            frame = np.zeros(
                (h, w, 3),
                dtype="uint8"
            )

            cv2.putText(
                frame,
                "ATHENA NO DISPONIBLE",
                (80, h // 2 - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (30, 30, 180),
                2,
            )

            cv2.putText(
                frame,
                "vision_env no encontrado",
                (120, h // 2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (60, 60, 100),
                1,
            )

            _, encoded = cv2.imencode(
                ".jpg",
                frame
            )

            self.buffer.write(
                encoded.tobytes()
            )

        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════════
# ATHENA MANAGER
# ═════════════════════════════════════════════════════════════════════

class AthenaManager:
    """
    Gestiona múltiples cámaras de forma independiente.

    Estructura:

        workers[cam_id]
            ↓
        AthenaThread

        buffers[cam_id]
            ↓
        AthenaBuffer

    Ejemplo:

        cam 1 → worker 1 → buffer 1
        cam 2 → worker 2 → buffer 2
        cam 3 → worker 3 → buffer 3
    """

    def __init__(self):

        # -------------------------------------------------------------
        # Workers por cámara
        # -------------------------------------------------------------

        self.workers = {}

        # -------------------------------------------------------------
        # Buffer de salida por cámara
        # -------------------------------------------------------------

        self.buffers = {}

        # -------------------------------------------------------------
        # Información adicional de cada cámara
        # -------------------------------------------------------------

        self.camera_info = {}

        # Telemetría de sesiones activas y finalizadas, sólo en memoria.
        self._diag_lock = threading.Lock()
        self.diagnostics = {}
        self.completed_diagnostics = {}

        # -------------------------------------------------------------
        # Lock principal
        # -------------------------------------------------------------

        self.lock = threading.RLock()

        # -------------------------------------------------------------
        # Cola global de eventos.
        #
        # Cada evento contiene cam_id.
        # -------------------------------------------------------------

        self.event_queue = queue.Queue(
            maxsize=200
        )

    # ═════════════════════════════════════════════════════════════════
    # START
    # ═════════════════════════════════════════════════════════════════

    def start(
        self,
        cam_id: int,
        source,
        confidence: float = 0.50,
        mode: str = "acceso",
        tripwire: float = 0.55,
        client_id: Optional[str] = None,
        request_started_at: Optional[float] = None,
    ):
        """
        Inicia Athena para una cámara.

        Parámetros:

            cam_id:
                ID de la cámara.

            source:
                RTSP, HTTP, archivo, webcam, etc.

            confidence:
                Confianza mínima de detección.

            mode:
                acceso / evasion / etc.

            tripwire:
                Umbral del tripwire.

            client_id:
                ID del WebSocket cuando source == webcam.
        """

        cam_id = int(cam_id)

        with self.lock:

            # ---------------------------------------------------------
            # Si la cámara ya estaba ejecutándose,
            # detener solamente esa cámara.
            # ---------------------------------------------------------

            existing = self.workers.get(
                cam_id
            )

            if existing:

                logger.info(
                    f"Athena cam={cam_id} "
                    f"ya estaba activa. "
                    f"Reiniciando..."
                )

                existing.stop()

        # Esperar fuera del lock para no bloquear otras operaciones.
        if existing and existing.is_alive():

            existing.join(
                timeout=5
            )

        with self.lock:

            if existing:
                if self.workers.get(cam_id) is not existing:
                    logger.warning(
                        f"No se pudo reiniciar la cámara {cam_id}: el worker registrado cambió durante la espera."
                    )
                    raise RuntimeError(
                        f"No se pudo reiniciar la cámara {cam_id}: el worker registrado cambió durante la espera."
                    )

                if existing.is_alive():
                    logger.warning(
                        f"No se pudo reiniciar la cámara {cam_id}: el hilo anterior AthenaThread "
                        f"continúa en ejecución tras el tiempo de espera (5s)."
                    )
                    raise RuntimeError(
                        f"No se pudo reiniciar la cámara {cam_id}: el hilo anterior no terminó en el tiempo esperado."
                    )

                self.workers.pop(
                    cam_id,
                    None
                )

                self.buffers.pop(
                    cam_id,
                    None
                )

                self.camera_info.pop(
                    cam_id,
                    None
                )
                try:
                    camera_manager.remove(cam_id)
                except Exception:
                    pass

                self._archive_session(cam_id, getattr(existing, "session_id", None))
            elif self.workers.get(cam_id) is not None:
                logger.warning(
                    f"No se pudo iniciar la cámara {cam_id}: otro worker fue registrado concurrentemente."
                )
                raise RuntimeError(
                    f"No se pudo iniciar la cámara {cam_id}: conflicto de concurrencia al iniciar la cámara."
                )

            # ---------------------------------------------------------
            # Determinar si es webcam.
            # ---------------------------------------------------------

            webcam_mode = (
                str(source)
                .strip()
                .lower()
                == "webcam"
            )

            # ---------------------------------------------------------
            # Fuente interna para webcam.
            #
            # IMPORTANTE:
            #
            # Cada webcam debe usar SU client_id.
            # Así nunca se mezclan las cámaras.
            # ---------------------------------------------------------

            if webcam_mode:

                if not client_id:

                    raise ValueError(
                        f"La cámara {cam_id} "
                        f"es webcam pero no recibió "
                        f"client_id."
                    )

                safe_client_id = quote(
                    str(client_id),
                    safe=""
                )

                # R03: Generar ticket efímero de streaming para el pipeline local de Athena
                try:
                    from services.auth_service import issue_stream_ticket
                    internal_ticket = issue_stream_ticket(user_id=1, cam_id=cam_id, ttl_seconds=86400)
                    ticket_param = f"&stream_ticket={internal_ticket}"
                except Exception as e:
                    logger.warning(f"[AthenaEngine] No se pudo generar ticket de streaming para webcam: {e}")
                    ticket_param = ""

                engine_source = (
                    "http://127.0.0.1:5000"
                    "/api/camaras/client/mjpeg"
                    f"?client_id={safe_client_id}"
                    f"{ticket_param}"
                )

            else:

                engine_source = source

            # ---------------------------------------------------------
            # Crear buffer independiente.
            # ---------------------------------------------------------

            buffer = AthenaBuffer()

            started_at = request_started_at if request_started_at is not None else time.perf_counter()
            diagnostics = {
                "cam_id": cam_id,
                "mode": mode,
                "session_id": uuid.uuid4().hex,
                "started_at": started_at,
                "started_time": time.time(),
                "is_active": True,
                "milestones_s": {"connect_request_s": 0.0},
                "worker": None,
                "last_report_at": None,
            }
            with self._diag_lock:
                self.diagnostics[cam_id] = diagnostics

            self.buffers[
                cam_id
            ] = buffer

            # ---------------------------------------------------------
            # Crear worker independiente.
            # ---------------------------------------------------------

            worker = AthenaThread(

                cam_id=cam_id,

                source=engine_source,

                buffer=buffer,

                event_queue=self.event_queue,

                confidence=confidence,

                mode=mode,

                tripwire=tripwire,

                client_id=client_id,

                diagnostics=diagnostics,
                diag_lock=self._diag_lock,
                on_session_end=self._archive_session,
            )

            # ---------------------------------------------------------
            # Registrar antes de iniciar.
            # ---------------------------------------------------------

            self.workers[
                cam_id
            ] = worker

            self.camera_info[
                cam_id
            ] = {
                "source": source,
                "engine_source": engine_source,
                "mode": mode,
                "confidence": confidence,
                "tripwire": tripwire,
                "webcam_mode": webcam_mode,
                "client_id": client_id,
            }

            # ---------------------------------------------------------
            # Registrar en CameraManager.
            # ---------------------------------------------------------

            try:

                camera_manager.add(
                    cam_id,
                    worker
                )

            except Exception as e:

                logger.warning(
                    f"No se pudo registrar "
                    f"cam={cam_id} en CameraManager: "
                    f"{e}"
                )

            # ---------------------------------------------------------
            # Iniciar thread de forma protegida.
            # Si falla, limpiar referencias y archivar diagnóstico.
            # ---------------------------------------------------------

            try:
                worker.start()
            except Exception as e:
                logger.error(
                    f"Error al iniciar hilo AthenaThread para cam={cam_id}: {e}",
                    exc_info=True
                )
                self.workers.pop(cam_id, None)
                self.buffers.pop(cam_id, None)
                self.camera_info.pop(cam_id, None)
                try:
                    camera_manager.remove(cam_id)
                except Exception:
                    pass
                self._archive_session(
                    cam_id,
                    diagnostics.get("session_id"),
                    fallback_diag=diagnostics
                )
                raise

            logger.info(
                f"✓ Athena iniciado "
                f"cam={cam_id} "
                f"source={source!r} "
                f"mode={mode} "
                f"webcam={webcam_mode} "
                f"client_id={client_id}"
            )

            return worker

    # ═════════════════════════════════════════════════════════════════
    # STOP
    # ═════════════════════════════════════════════════════════════════

    def stop(self, cam_id):
        """
        Detiene solamente la cámara indicada.
        """

        cam_id = int(cam_id)

        with self.lock:

            worker = self.workers.get(
                cam_id
            )

            if not worker:

                logger.info(
                    f"Athena cam={cam_id} "
                    f"no estaba activa."
                )

                return False

            logger.info(
                f"Deteniendo Athena cam={cam_id}"
            )

            worker.stop()

        # -------------------------------------------------------------
        # Esperar fuera del lock.
        # -------------------------------------------------------------

        if worker.is_alive():

            worker.join(
                timeout=5
            )

        # -------------------------------------------------------------
        # Comprobar si el hilo terminó realmente.
        # -------------------------------------------------------------

        with self.lock:

            if self.workers.get(cam_id) is not worker:
                logger.warning(
                    f"Athena cam={cam_id}: el worker registrado cambió durante la detención. "
                    f"No se modifican las referencias ni el diagnóstico actual."
                )
                return False

            if worker.is_alive():
                logger.warning(
                    f"AthenaThread cam={cam_id} no terminó en el tiempo esperado (5s); "
                    f"permanece activo. La sesión diagnóstica se mantiene activa."
                )
                return False

            # ---------------------------------------------------------
            # Limpiar referencias y archivar si terminó.
            # ---------------------------------------------------------

            self.workers.pop(
                cam_id,
                None
            )

            buffer = self.buffers.pop(
                cam_id,
                None
            )

            self.camera_info.pop(
                cam_id,
                None
            )
            self._archive_session(cam_id, getattr(worker, "session_id", None))

            if buffer:

                buffer.clear()

            try:

                camera_manager.remove(
                    cam_id
                )

            except Exception:
                pass

        logger.info(
            f"✓ Athena detenido cam={cam_id}"
        )

        return True

    # ═════════════════════════════════════════════════════════════════
    # STOP ALL
    # ═════════════════════════════════════════════════════════════════

    def stop_all(self):
        """
        Detiene todas las cámaras.
        """

        with self.lock:

            cam_ids = list(
                self.workers.keys()
            )

        for cam_id in cam_ids:

            try:

                self.stop(cam_id)

            except Exception as e:

                logger.error(
                    f"Error deteniendo "
                    f"cam={cam_id}: {e}"
                )

    # ═════════════════════════════════════════════════════════════════
    # IS RUNNING
    # ═════════════════════════════════════════════════════════════════

    def is_running(self, cam_id=None) -> bool:
        """
        Comprueba si Athena está ejecutándose.

        Si cam_id se proporciona:
            devuelve el estado de esa cámara.

        Si no:
            devuelve True si existe al menos una cámara activa.
        """

        with self.lock:

            if cam_id is not None:

                cam_id = int(cam_id)

                worker = self.workers.get(
                    cam_id
                )

                return bool(
                    worker
                    and worker.is_running
                )

            # ---------------------------------------------------------
            # Cualquier cámara activa.
            # ---------------------------------------------------------

            return any(
                worker.is_running
                for worker in self.workers.values()
            )

    # ═════════════════════════════════════════════════════════════════
    # ACTIVE CAMERAS
    # ═════════════════════════════════════════════════════════════════

    def active_cameras(self):
        """
        Retorna los IDs de las cámaras activas.
        """

        with self.lock:

            return [
                cam_id
                for cam_id, worker
                in self.workers.items()
                if worker.is_running
            ]

    # ═════════════════════════════════════════════════════════════════
    # GET BUFFER
    # ═════════════════════════════════════════════════════════════════

    def get_buffer(self, cam_id) -> Optional[AthenaBuffer]:
        """
        Obtiene el buffer correspondiente a una cámara.
        """

        cam_id = int(cam_id)

        with self.lock:

            return self.buffers.get(
                cam_id
            )

    def diagnostics_status(self, cam_id: Optional[int] = None) -> dict:
        """
        Retorna la telemetría en memoria de sesiones activas y finalizadas.
        Garantiza copias profundas e independientes frente a accesos concurrentes.
        No expone credenciales, rutas ni IPs de las fuentes.
        """
        target_cam = int(cam_id) if cam_id is not None else None
        now_perf = time.perf_counter()

        with self._diag_lock:
            active_entries = [
                (sid, copy.deepcopy(diag))
                for sid, diag in self.diagnostics.items()
                if target_cam is None or diag.get("cam_id") == target_cam
            ]
            completed_entries = [
                (sid, copy.deepcopy(diag))
                for sid, diag in self.completed_diagnostics.items()
                if target_cam is None or diag.get("cam_id") == target_cam
            ]

        result = {}
        for _, item in active_entries:
            started_at = item.pop("started_at", None)
            item.pop("started_time", None)
            item["is_active"] = True
            item["elapsed_s"] = (now_perf - started_at) if started_at is not None else 0.0
            for sensitive_key in ("source", "engine_source", "ip", "url", "credentials"):
                item.pop(sensitive_key, None)
            result[item["session_id"]] = item

        for _, item in completed_entries:
            started_at = item.pop("started_at", None)
            item.pop("started_time", None)
            item["is_active"] = False
            item["elapsed_s"] = item.get("duration_s", 0.0)
            for sensitive_key in ("source", "engine_source", "ip", "url", "credentials"):
                item.pop(sensitive_key, None)
            result[item["session_id"]] = item

        return {"sessions": result}

    def _archive_session(
        self,
        cam_id: int,
        session_id: Optional[str] = None,
        fallback_diag: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Archiva la sesión diagnóstica de forma idempotente y segura ante concurrencia.
        Si se especifica session_id, solo archiva si coincide con la sesión activa actual
        de la cámara, evitando sobrescribir sesiones nuevas con hilos anteriores lentos.
        """
        cam_id = int(cam_id)
        with self._diag_lock:
            # 1. Si la sesión ya fue archivada previamente, no duplicar
            if session_id and session_id in self.completed_diagnostics:
                return self.completed_diagnostics[session_id]

            # 2. Localizar la sesión a archivar
            current = self.diagnostics.get(cam_id)
            if current and (session_id is None or current.get("session_id") == session_id):
                diag = self.diagnostics.pop(cam_id)
            elif fallback_diag and (session_id is None or fallback_diag.get("session_id") == session_id):
                diag = fallback_diag
            else:
                return None

            # 3. Registrar duración real y estado finalizado
            diag["ended_at"] = time.time()
            started_at = diag.get("started_at", time.perf_counter())
            diag["duration_s"] = max(0.0, time.perf_counter() - started_at)
            diag["is_active"] = False

            sid = diag.get("session_id")
            if sid:
                self.completed_diagnostics[sid] = diag
                self._prune_completed_diagnostics()

            return diag

    def _prune_completed_diagnostics(self):
        """Limita la retención diagnóstica a 20 sesiones finalizadas más recientes."""
        overflow = len(self.completed_diagnostics) - 20
        if overflow > 0:
            oldest = sorted(
                self.completed_diagnostics.keys(),
                key=lambda sid: self.completed_diagnostics[sid].get("ended_at", 0.0)
            )
            for session_id in oldest[:overflow]:
                self.completed_diagnostics.pop(session_id, None)

    # ═════════════════════════════════════════════════════════════════
    # STATUS
    # ═════════════════════════════════════════════════════════════════

    def status(self) -> dict:
        """
        Estado completo de Athena.

        Ejemplo:

        {
            "running": true,
            "cameras": {
                "1": {
                    "running": true,
                    "mode": "evasion",
                    "webcam_mode": true
                },
                "2": {
                    "running": true,
                    "mode": "acceso",
                    "webcam_mode": false
                }
            }
        }
        """

        with self.lock:

            cameras = {}

            for cam_id, worker in self.workers.items():

                info = self.camera_info.get(
                    cam_id,
                    {}
                )

                cameras[str(cam_id)] = {
                    "running": worker.is_running,

                    "mode": info.get(
                        "mode",
                        worker.mode
                    ),

                    "webcam_mode": info.get(
                        "webcam_mode",
                        False
                    ),

                    "client_id": info.get(
                        "client_id"
                    ),

                    "source": info.get(
                        "source"
                    ),

                    "confidence": info.get(
                        "confidence",
                        worker.confidence
                    ),

                    "tripwire": info.get(
                        "tripwire",
                        worker.tripwire
                    ),

                    "buffer_age": (
                        self.buffers[cam_id].age()
                        if cam_id in self.buffers
                        else None
                    ),
                }

            return {
                "running": any(
                    camera["running"]
                    for camera in cameras.values()
                ),

                "cameras": cameras,

                "active_cameras": [
                    int(cam_id)
                    for cam_id, camera
                    in cameras.items()
                    if camera["running"]
                ],

                "camera_count": len(
                    cameras
                ),

                "venv_ok": os.path.isfile(
                    _VENV_PYTHON
                ),

                "venv_path": _VENV_PYTHON,
            }

    # ═════════════════════════════════════════════════════════════════
    # GENERATE STREAM
    # ═════════════════════════════════════════════════════════════════

    def generate_stream(self, cam_id):
        """
        Generador MJPEG para UNA cámara.

        Flask lo utiliza mediante:

            /api/camaras/<cam_id>/stream

        Cada conexión recibe únicamente los frames
        pertenecientes a ese cam_id.
        """

        cam_id = int(cam_id)

        boundary = (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
        )

        # -------------------------------------------------------------
        # Obtener buffer de la cámara.
        # -------------------------------------------------------------

        buffer = self.get_buffer(
            cam_id
        )

        if buffer is None:

            logger.warning(
                f"generate_stream: "
                f"no existe buffer para cam={cam_id}"
            )

            return

        last_ts = -1.0

        # -------------------------------------------------------------
        # Streaming continuo.
        # -------------------------------------------------------------

        while True:

            # ---------------------------------------------------------
            # Esperar un frame nuevo.
            # ---------------------------------------------------------

            buffer.wait_for_new(
                timeout=0.05
            )

            # ---------------------------------------------------------
            # Leer frame.
            # ---------------------------------------------------------

            frame_bytes, ts = (
                buffer.read_with_ts()
            )

            # ---------------------------------------------------------
            # Si no hay frame, continuar.
            # ---------------------------------------------------------

            if not frame_bytes:

                # Si la cámara ya no existe, terminar.
                with self.lock:

                    if cam_id not in self.buffers:

                        logger.info(
                            f"Stream cam={cam_id} "
                            f"finalizado."
                        )

                        break

                continue

            # ---------------------------------------------------------
            # Evitar enviar el mismo frame dos veces.
            # ---------------------------------------------------------

            if ts == last_ts:

                continue

            last_ts = ts

            with self._diag_lock:
                diagnostics = self.diagnostics.get(cam_id)
                if diagnostics is not None:
                    ms = diagnostics.setdefault("milestones_s", {})
                    if "first_mjpeg_yield_s" not in ms:
                        started_at = diagnostics.get("started_at", time.perf_counter())
                        ms["first_mjpeg_yield_s"] = time.perf_counter() - started_at

            # ---------------------------------------------------------
            # MJPEG multipart.
            # ---------------------------------------------------------

            yield (
                boundary
                + frame_bytes
                + b"\r\n"
            )


# ═════════════════════════════════════════════════════════════════════
# INSTANCIA GLOBAL
# ═════════════════════════════════════════════════════════════════════

athena = AthenaManager()
