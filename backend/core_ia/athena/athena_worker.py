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

# --- Importaciones IA ---
def load_imports(mode):
    mods = {}
    try:
        import cv2; mods['cv2'] = cv2; logger.info('cv2 %s cargado' % cv2.__version__)
    except ImportError as e:
        logger.critical('cv2 no disponible: %s' % e); sys.exit(1)
    try:
        import numpy as np; mods['np'] = np
    except ImportError as e:
        logger.critical('numpy no disponible: %s' % e); sys.exit(1)

    if mode == 'evasion':
        try:
            from detectors.person_tracker import detectar_personas_tracking
            mods['tracker'] = detectar_personas_tracking
            logger.info('Tracker ByteTrack cargado')
        except Exception as e:
            logger.warning('Tracker no disponible: %s' % e)
        try:
            from detectors.evasion_detector import EvasionDetector
            mods['EvasionDetector'] = EvasionDetector
            logger.info('Detector evasion cargado')
        except Exception as e:
            logger.warning('Detector evasion no disponible: %s' % e)
    else:
        try:
            from detectors.person_detector import detectar_persona
            mods['detectar_persona'] = detectar_persona
            logger.info('Detector persona cargado')
        except Exception as e:
            logger.warning('Detector persona no disponible: %s' % e)
        try:
            from detectors.pose_detector import detectar_brazo
            mods['detectar_brazo'] = detectar_brazo
            logger.info('Detector pose cargado')
        except Exception as e:
            logger.warning('Detector pose no disponible: %s' % e)
        # MediaPipe Hands: DESACTIVADO para mejor rendimiento
        # from detectors.hand_detector import detectar_mano
        # FaceMesh: DESACTIVADO para mejor rendimiento
        # from detectors.face_detector import detectar_rostro
        try:
            from detectors.card_detector import detectar_tarjeta
            mods['detectar_tarjeta'] = detectar_tarjeta
            logger.info('Detector tarjeta cargado')
        except Exception as e:
            logger.warning('Detector tarjeta no disponible: %s' % e)
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
    def __init__(self, cv2, source):
        self.cv2 = cv2
        self.source = source
        self.es_archivo = _es_archivo(str(source))
        if not self.es_archivo:
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|fflags;nobuffer|flags;low_delay'
        self.cap = cv2.VideoCapture(source)
        if self.cap.isOpened():
            if not self.es_archivo:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.ret = False
        self.frame = None
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
                ret, frame = self.cap.read()
                if ret:
                    fails = 0
                    with self.lock:
                        self.ret = True
                        self.frame = frame
                    if self.es_archivo:
                        time.sleep(delay)
                else:
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
        with self.lock:
            if self.frame is not None:
                return self.ret, self.frame.copy()
            return True, None

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
    args = parser.parse_args()

    if args.source.isdigit():
        source = int(args.source)
    else:
        source = args.source

    cam_id = args.cam_id
    mode   = args.mode.strip().lower()
    logger.info('Worker iniciado: source=%r mode=%s cam_id=%d' % (source, mode, cam_id))

    mods = load_imports(mode)
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

    while True:
        if cap is None or not cap.isOpened():
            logger.info('Conectando a: %s' % source)
            cap = FastCameraReader(cv2, source)
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

        ret, frame = cap.read()
        if frame is None:
            time.sleep(0.01)
            continue
        if not ret:
            logger.warning('Fuente perdida -- reconectando')
            cap.release(); cap = None
            send_frame(placeholder_frame(np, cv2, source))
            time.sleep(retry_delay)
            continue

        h, w = frame.shape[:2]
        if w > 480:
            scale = 480 / w
            frame = cv2.resize(frame, (480, int(h*scale)), interpolation=cv2.INTER_LINEAR)

        if mode == 'evasion':
            estado = {'persona': False}
            tracks = []
            if 'tracker' in mods:
                try:
                    logger.info('Procesando frame con ByteTrack...')
        
                    inicio_tracker = time.time()

                    estado['persona'], tracks, frame = mods['tracker'](frame)

                    tiempo_tracker = time.time() - inicio_tracker

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
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                alertas = ev_detector.analizar(tracks, frame, rgb)
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

            draw_overlay(cv2, frame, estado, source, mode)
            if tracks:
                cv2.putText(frame, 'Personas: %d' % len(tracks), (10, 36),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0,220,255), 1, cv2.LINE_AA)
        else:
            estado = {'persona': False, 'brazo': False, 'tarjeta': False}
            if 'detectar_persona' in mods:
                try:
                    estado['persona'], frame = mods['detectar_persona'](frame)
                except Exception as e:
                    logger.debug('persona: %s' % e)
            if estado['persona']:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if 'detectar_brazo' in mods:
                    try:
                        estado['brazo'], frame = mods['detectar_brazo'](frame, rgb)
                    except Exception as e:
                        logger.debug('brazo: %s' % e)
                if 'detectar_tarjeta' in mods:
                    try:
                        estado['tarjeta'], frame = mods['detectar_tarjeta'](frame)
                    except Exception as e:
                        logger.debug('tarjeta: %s' % e)
            draw_overlay(cv2, frame, estado, source, mode)
            if edge:
                for ev in edge.process(estado, cam_id):
                    send_event(ev)

        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        if ok:
            send_frame(buf.tobytes())

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('Worker detenido por senal')
    except Exception as e:
        logger.critical('Error fatal: ' + str(e) + '\n' + traceback.format_exc())
        sys.exit(1)
