import sys, os, json, time, struct, argparse, logging, traceback
import threading
from evidence.capture_manager import capture_manager

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format='[WORKER %(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

WORKER_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKER_DIR not in sys.path:
    sys.path.insert(0, WORKER_DIR)

_VIDEO_EXT = {'.mp4', '.avi', '.mkv', '.mov', '.webm', '.ts', '.flv'}

def _es_archivo(src):
    _, ext = os.path.splitext(str(src).lower())
    return ext in _VIDEO_EXT

# --- Protocolo binario ---
def write_msg(t, p):
    hdr = struct.pack('>BI', t, len(p))
    try:
        sys.stdout.buffer.write(hdr + p)
        sys.stdout.buffer.flush()
    except (BrokenPipeError, OSError):
        sys.exit(0)

def send_frame(b): write_msg(0x01, b)
def send_event(e): write_msg(0x02, json.dumps(e, ensure_ascii=False).encode('utf-8'))
def send_heartbeat(): write_msg(0xFF, b'')
def send_metrics(metrics): write_msg(0x03, json.dumps(metrics, ensure_ascii=False).encode('utf-8'))


class WorkerMetrics:
    """Telemetría acumulada del worker; no controla ni altera el procesamiento."""
    def __init__(self, cam_id, mode, session_id):
        self.cam_id, self.mode, self.session_id = cam_id, mode, session_id
        self.started_at = time.perf_counter()
        self._lock = threading.Lock()
        self.milestones = {'worker_started_s': 0.0}
        self.counts = {'captured': 0, 'processed': 0, 'transmitted': 0,
                       'consumer_repeats': 0, 'capture_read_failures': 0}
        self.timings = {}
        self._window = {'captured': 0, 'processed': 0, 'transmitted': 0}
        self._last_summary = self.started_at
        self._first = set()
        self.latest_capture_sequence = 0
        self._process = None
        try:
            import psutil
            self._process = psutil.Process(os.getpid())
            self._process.cpu_percent(None)  # Inicializa el intervalo de CPU.
        except Exception:
            pass

    def milestone(self, name):
        now = time.perf_counter()
        with self._lock:
            if name not in self.milestones:
                self.milestones[name] = now - self.started_at

    def observe(self, name, seconds):
        value = seconds * 1000.0
        with self._lock:
            item = self.timings.get(name)
            if item is None:
                item = {'count': 0, 'total_ms': 0.0, 'max_ms': 0.0}
                self.timings[name] = item
            item['count'] += 1
            item['total_ms'] += value
            if value > item['max_ms']:
                item['max_ms'] = value

    def count(self, name, amount=1):
        with self._lock:
            self.counts[name] = self.counts.get(name, 0) + amount
            if name in self._window:
                self._window[name] += amount

    def first(self, name):
        now = time.perf_counter()
        with self._lock:
            if name not in self._first:
                self._first.add(name)
                if name not in self.milestones:
                    self.milestones[name] = now - self.started_at

    def set_capture_sequence(self, sequence):
        with self._lock:
            self.latest_capture_sequence = sequence

    def snapshot(self):
        # 1. Copia consistente de métricas bajo lock (ultrarrápida en memoria)
        now = time.perf_counter()
        with self._lock:
            elapsed = max(now - self._last_summary, 0.000001)
            milestones_copy = dict(self.milestones)
            counts_copy = dict(self.counts)
            seq_copy = self.latest_capture_sequence
            window_counts = dict(self._window)
            self._window = {'captured': 0, 'processed': 0, 'transmitted': 0}
            self._last_summary = now
            timings_raw = {
                k: {'count': v['count'], 'total_ms': v['total_ms'], 'max_ms': v['max_ms']}
                for k, v in self.timings.items()
            }

        # 2. Consultas potencialmente costosas de recursos del sistema FUERA del lock
        resources = {'available': False}
        try:
            if self._process is None:
                raise RuntimeError('psutil no disponible')
            resources = {
                'available': True,
                'cpu_percent': self._process.cpu_percent(None),
                'rss_bytes': self._process.memory_info().rss,
                'num_threads': self._process.num_threads(),
            }
        except Exception:
            pass

        # 3. Cálculo de promedios de tiempos fuera del lock
        timings = {
            name: {
                'count': val['count'],
                'total_ms': val['total_ms'],
                'max_ms': val['max_ms'],
                'avg_ms': (val['total_ms'] / val['count']) if val['count'] else 0.0,
            }
            for name, val in timings_raw.items()
        }

        # 4. Construcción del resultado consistente
        return {
            'cam_id': self.cam_id,
            'mode': self.mode,
            'session_id': self.session_id,
            'uptime_s': now - self.started_at,
            'milestones_s': milestones_copy,
            'counts': counts_copy,
            'latest_capture_sequence': seq_copy,
            'fps': {k: v / elapsed for k, v in window_counts.items()},
            'window_s': elapsed,
            'timings_ms': timings,
            'resources': resources,
        }

    def emit_if_due(self):
        """
        Emite métricas al backend si transcurrieron al menos 5.0s desde el último reporte.
        Depende exclusivamente del avance del ciclo principal del worker.
        No utiliza hilos adicionales ni interrumpe el flujo normal de frames.
        """
        now = time.perf_counter()
        with self._lock:
            due = (now - self._last_summary >= 5.0)
        if due:
            data = self.snapshot()
            send_metrics(data)

# --- Importaciones IA ---
def load_imports(mode, metrics):
    mods = {}
    metrics.milestone('imports_started_s')
    try:
        t = time.perf_counter()
        import cv2; mods['cv2'] = cv2; logger.info('cv2 %s cargado' % cv2.__version__)
        metrics.observe('import_cv2', time.perf_counter() - t)
    except ImportError as e:
        logger.critical('cv2 no disponible: %s' % e); sys.exit(1)
    try:
        t = time.perf_counter()
        import numpy as np; mods['np'] = np
        metrics.observe('import_numpy', time.perf_counter() - t)
    except ImportError as e:
        logger.critical('numpy no disponible: %s' % e); sys.exit(1)

    if mode == 'evasion':
        try:
            t = time.perf_counter()
            metrics.milestone('person_tracker_model_load_started_s')
            from detectors.person_tracker import detectar_personas_tracking
            mods['tracker'] = detectar_personas_tracking
            metrics.observe('load_person_tracker_model', time.perf_counter() - t)
            metrics.milestone('person_tracker_model_load_finished_s')
            logger.info('Tracker ByteTrack cargado')
        except Exception as e:
            logger.warning('Tracker no disponible: %s' % e)
        try:
            t = time.perf_counter()
            metrics.milestone('evasion_pose_model_load_started_s')
            from detectors.evasion_detector import EvasionDetector
            mods['EvasionDetector'] = EvasionDetector
            metrics.observe('load_evasion_pose_model', time.perf_counter() - t)
            metrics.milestone('evasion_pose_model_load_finished_s')
            logger.info('Detector evasion cargado')
        except Exception as e:
            logger.warning('Detector evasion no disponible: %s' % e)
    else:
        try:
            t = time.perf_counter()
            metrics.milestone('person_model_load_started_s')
            from detectors.person_detector import detectar_persona
            mods['detectar_persona'] = detectar_persona
            metrics.observe('load_person_model', time.perf_counter() - t)
            metrics.milestone('person_model_load_finished_s')
            logger.info('Detector persona cargado')
        except Exception as e:
            logger.warning('Detector persona no disponible: %s' % e)
        try:
            t = time.perf_counter()
            metrics.milestone('pose_model_load_started_s')
            from detectors.pose_detector import detectar_brazo
            mods['detectar_brazo'] = detectar_brazo
            metrics.observe('load_pose_model', time.perf_counter() - t)
            metrics.milestone('pose_model_load_finished_s')
            logger.info('Detector pose cargado')
        except Exception as e:
            logger.warning('Detector pose no disponible: %s' % e)
        # MediaPipe Hands: DESACTIVADO para mejor rendimiento
        # from detectors.hand_detector import detectar_mano
        # FaceMesh: DESACTIVADO para mejor rendimiento
        # from detectors.face_detector import detectar_rostro
        try:
            t = time.perf_counter()
            metrics.milestone('card_model_load_started_s')
            from detectors.card_detector import detectar_tarjeta
            mods['detectar_tarjeta'] = detectar_tarjeta
            metrics.observe('load_card_model', time.perf_counter() - t)
            metrics.milestone('card_model_load_finished_s')
            logger.info('Detector tarjeta cargado')
        except Exception as e:
            logger.warning('Detector tarjeta no disponible: %s' % e)
    metrics.milestone('imports_finished_s')
    return mods

# --- Placeholder frame ---
def placeholder_frame(np, cv2, source):
    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype='uint8')
    ts = time.strftime('%H:%M:%S')
    cv2.putText(frame, 'SIN SENAL', (w//2-100, h//2-10),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (50,50,50), 2)
    cv2.putText(frame, 'Fuente: ' + str(source)[:40], (20, h-40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40,40,40), 1)
    cv2.putText(frame, ts, (20, h-20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40,40,40), 1)
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return buf.tobytes()

# --- HUD Overlay ---
def draw_overlay(cv2, frame, estado, cam_source, mode):
    h, w = frame.shape[:2]
    ts = time.strftime('%H:%M:%S')
    label = 'EVASION' if mode == 'evasion' else 'ACCESO'
    cv2.putText(frame, ts + '  [' + label + ']  SRC:' + str(cam_source)[:18],
                (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180,180,180), 1, cv2.LINE_AA)
    if mode == 'acceso':
        labels = [
            ('PERSONA', estado.get('persona', False), (0,200,255)),
            ('BRAZO',   estado.get('brazo',   False), (255,165,0)),
            ('TARJETA', estado.get('tarjeta', False), (0,255,100)),
        ]
        for i, (lbl, activo, color) in enumerate(labels):
            clr = color if activo else (45,45,45)
            texto = '[' + lbl + ']' if activo else lbl
            cv2.putText(frame, texto, (10, h - 20 - i*18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, clr, 1, cv2.LINE_AA)

# --- EdgeDetector ---
class EdgeDetector:
    def __init__(self, cooldown=3.0):
        self.prev = {'persona': False, 'brazo': False, 'tarjeta': False}
        self.last_acceso = 0.0
        self.cooldown = cooldown

    def process(self, estado, cam_id):
        eventos = []
        now = time.time()
        p = self.prev
        if estado['persona'] and not p['persona']:
            eventos.append({'tipo': 'PERSONA_DETECTADA', 'descripcion': 'Persona detectada',
                             'cam_id': cam_id, 'ts': now})
        if estado.get('brazo') and not p['brazo']:
            eventos.append({'tipo': 'BRAZO_ARRIBA', 'descripcion': 'Brazo levantado',
                             'cam_id': cam_id, 'ts': now})
        if estado.get('tarjeta') and not p['tarjeta']:
            eventos.append({'tipo': 'TARJETA_VALIDA', 'descripcion': 'Tarjeta valida',
                             'cam_id': cam_id, 'ts': now})
        if estado['persona'] and estado.get('brazo') and estado.get('tarjeta'):
            if now - self.last_acceso > self.cooldown:
                self.last_acceso = now
                eventos.append({'tipo': 'ACCESO_CONCEDIDO', 'descripcion': 'Acceso concedido',
                                 'cam_id': cam_id, 'ts': now})
        self.prev = {'persona': estado['persona'],
                     'brazo': estado.get('brazo', False),
                     'tarjeta': estado.get('tarjeta', False)}
        return eventos

# --- FastCameraReader ---
class FastCameraReader:
    def __init__(self, cv2, source, metrics):
        self.cv2 = cv2
        self.source = source
        self.metrics = metrics
        self.es_archivo = _es_archivo(str(source))
        if not self.es_archivo:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|fflags;nobuffer|flags;low_delay'
        self.metrics.milestone('videocapture_open_started_s')
        t = time.perf_counter(); self.cap = cv2.VideoCapture(source)
        self.metrics.observe('videocapture_open', time.perf_counter() - t)
        self.metrics.milestone('videocapture_open_finished_s')
        if self.cap.isOpened():
            if not self.es_archivo:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.ret = False
        self.frame = None
        self.sequence = 0
        self.running = True
        self.lock = threading.Lock()
        if self.cap.isOpened():
            self.thread = threading.Thread(target=self._update, daemon=True)
            self.thread.start()

    def _update(self):
        delay = 1.0 / max(self.fps, 1.0) if self.es_archivo else 0.0
        fails = 0
        while self.running:
            if self.cap.isOpened():
                t = time.perf_counter(); ret, frame = self.cap.read()
                self.metrics.observe('capture_read', time.perf_counter() - t)
                if ret:
                    fails = 0
                    self.metrics.count('captured'); self.metrics.first('first_frame_captured_s')
                    with self.lock:
                        self.ret = True
                        self.frame = frame
                        self.sequence += 1
                        seq = self.sequence
                    self.metrics.set_capture_sequence(seq)
                    if self.es_archivo:
                        time.sleep(delay)
                else:
                    self.metrics.count('capture_read_failures')
                    if self.es_archivo:
                        self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
                        logger.info('Video terminado -- reiniciando en loop')
                        time.sleep(0.02)
                        fails = 0
                    else:
                        fails += 1
                        if fails > 10:
                            with self.lock:
                                self.ret = False
                            time.sleep(0.1)
            else:
                time.sleep(0.05)

    def isOpened(self): return self.cap.isOpened()

    def read(self):
        result = None
        ret = True
        seq = None
        t = time.perf_counter()
        with self.lock:
            if self.frame is not None:
                result = self.frame.copy()
                ret = self.ret
                seq = self.sequence
        dur = time.perf_counter() - t
        if result is not None:
            self.metrics.observe('frame_copy', dur)
            return ret, result, seq
        return True, None, None

    def release(self):
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2.0)
        self.cap.release()

# --- Loop Principal ---
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',     default='0')
    parser.add_argument('--confidence', type=float, default=0.50)
    parser.add_argument('--cam-id',     type=int,   default=0)
    parser.add_argument('--model',      default='yolov8n.pt')
    parser.add_argument('--mode',       default='acceso')
    parser.add_argument('--tripwire',   type=float, default=0.55)
    parser.add_argument('--session-id', default='')
    args = parser.parse_args()

    if args.source.isdigit():
        source = int(args.source)
    else:
        source = args.source

    cam_id = args.cam_id
    mode   = args.mode.strip().lower()
    metrics = WorkerMetrics(cam_id, mode, args.session_id)
    logger.info('Worker iniciado: source=%r mode=%s cam_id=%d' % (source, mode, cam_id))

    mods = load_imports(mode, metrics)
    cv2  = mods['cv2']
    np   = mods['np']

    edge = EdgeDetector() if mode == 'acceso' else None
    ev_detector = None
    if mode == 'evasion' and 'EvasionDetector' in mods:
        ev_detector = mods['EvasionDetector'](tripwire_y_ratio=args.tripwire)

    cap = None
    retry_delay = 2.0
    hb_interval = 10.0
    last_hb = time.time()
    last_consumed_sequence = None

    while True:
        if cap is None or not cap.isOpened():
            logger.info('Conectando a: %s' % source)
            cap = FastCameraReader(cv2, source, metrics)
            if not cap.isOpened():
                logger.warning('No se pudo abrir %r. Reintento en %.1fs' % (source, retry_delay))
                send_frame(placeholder_frame(np, cv2, source))
                time.sleep(retry_delay)
                cap.release(); cap = None
                continue
            logger.info('Fuente abierta OK')

        now = time.time()
        if now - last_hb >= hb_interval:
            send_heartbeat()
            last_hb = now

        t = time.perf_counter(); ret, frame, frame_sequence = cap.read()
        metrics.observe('frame_obtain', time.perf_counter() - t)
        if frame is None:
            time.sleep(0.01)
            continue
        if not ret:
            logger.warning('Fuente perdida -- reconectando')
            cap.release(); cap = None
            send_frame(placeholder_frame(np, cv2, source))
            time.sleep(retry_delay)
            continue

        if last_consumed_sequence is not None and frame_sequence == last_consumed_sequence:
            metrics.count('consumer_repeats')
        last_consumed_sequence = frame_sequence

        h, w = frame.shape[:2]
        if w > 480:
            t = time.perf_counter()
            scale = 480 / w
            frame = cv2.resize(frame, (480, int(h*scale)), interpolation=cv2.INTER_LINEAR)
            metrics.observe('resize', time.perf_counter() - t)

        if mode == 'evasion':
            estado = {'persona': False}
            tracks = []
            if 'tracker' in mods:
                try:
                    logger.info('Procesando frame con ByteTrack...')
        
                    inicio_tracker = time.perf_counter()

                    estado['persona'], tracks, frame = mods['tracker'](frame)

                    tiempo_tracker = time.perf_counter() - inicio_tracker
                    metrics.observe('bytetrack', tiempo_tracker)
                    metrics.first('first_inference_completed_s')

                    logger.info(
                    'ByteTrack OK - personas=%d - tiempo=%.2fs',
                    len(tracks),
                    tiempo_tracker
                    )

                except Exception as e:
                    logger.error(
                    'ERROR EN BYTE TRACK: %s\n%s',
                    e,
                    traceback.format_exc()
                    )

                    
            if estado['persona'] and ev_detector is not None:
                t = time.perf_counter(); rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                metrics.observe('bgr_to_rgb', time.perf_counter() - t)
                t = time.perf_counter()
                alertas = ev_detector.analizar(tracks, frame, rgb)
                metrics.observe('tripwire_evaluation', time.perf_counter() - t)
                for alerta in alertas:
                    alerta['cam_id'] = cam_id
                    # Guardar captura del evento detectado
                    evidencia = capture_manager.save_capture(
                    frame,
                    alerta
                    )

                    # Agregar la ruta de la evidencia al evento
                    if evidencia:
                        alerta['evidencia'] = evidencia
                    # Enviar evento al backend                    
                    send_event(alerta)

            t = time.perf_counter(); draw_overlay(cv2, frame, estado, source, mode)
            if tracks:
                cv2.putText(frame, 'Personas: %d' % len(tracks), (10, 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0,220,255), 1, cv2.LINE_AA)
            metrics.observe('annotations_hud', time.perf_counter() - t)
        else:
            estado = {'persona': False, 'brazo': False, 'tarjeta': False}
            if 'detectar_persona' in mods:
                try:
                    t = time.perf_counter()
                    estado['persona'], frame = mods['detectar_persona'](frame)
                    metrics.observe('yolo_person', time.perf_counter() - t)
                    metrics.first('first_inference_completed_s')
                except Exception as e:
                    logger.debug('persona: %s' % e)
            if estado['persona']:
                t = time.perf_counter(); rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                metrics.observe('bgr_to_rgb', time.perf_counter() - t)
                if 'detectar_brazo' in mods:
                    try:
                        t = time.perf_counter()
                        estado['brazo'], frame = mods['detectar_brazo'](frame, rgb)
                        metrics.observe('mediapipe_pose', time.perf_counter() - t)
                    except Exception as e:
                        logger.debug('brazo: %s' % e)
                if 'detectar_tarjeta' in mods:
                    try:
                        t = time.perf_counter()
                        estado['tarjeta'], frame = mods['detectar_tarjeta'](frame)
                        metrics.observe('yolo_card', time.perf_counter() - t)
                    except Exception as e:
                        logger.debug('tarjeta: %s' % e)
            t = time.perf_counter(); draw_overlay(cv2, frame, estado, source, mode)
            metrics.observe('annotations_hud', time.perf_counter() - t)
            if edge:
                for ev in edge.process(estado, cam_id):
                    ev['cam_id'] = cam_id
                    evidencia = capture_manager.save_capture(frame, ev)
                    if evidencia:
                        ev['evidencia'] = evidencia
                    send_event(ev)

        metrics.count('processed'); metrics.first('first_processing_completed_s')
        t = time.perf_counter(); ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        metrics.observe('jpeg_encode', time.perf_counter() - t)
        if ok:
            metrics.first('first_jpeg_encoded_s')
            t = time.perf_counter(); send_frame(buf.tobytes())
            metrics.observe('pipe_send_jpeg', time.perf_counter() - t)
            metrics.count('transmitted')
        metrics.emit_if_due()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('Worker detenido por senal')
    except Exception as e:
        logger.critical('Error fatal: ' + str(e) + '\n' + traceback.format_exc())
        sys.exit(1)
