from ultralytics import YOLO
import cv2

model = YOLO('yolov8n.pt')

_trayectorias = {}
_MAX_PUNTOS = 20

_PALETA = [
    (0,   200, 255), (0,   255,  80), (255, 100,   0),
    (200,   0, 255), (0,   100, 255), (255, 200,   0),
    (0,   255, 200), (255,  50, 100), (100, 255,   0),
]

def _color(tid):
    return _PALETA[tid % len(_PALETA)]

def detectar_personas_tracking(frame):
    global _trayectorias
    results = model.track(
        frame,
        persist=True,
        verbose=False,
        imgsz=320,
        classes=[0],
        conf=0.3,
        tracker='bytetrack.yaml',
    )
    persona_detectada = False
    tracks = []
    for r in results:
        if r.boxes is None or r.boxes.id is None:
            continue
        for box, tid_t in zip(r.boxes, r.boxes.id):
            tid   = int(tid_t.item())
            conf  = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            persona_detectada = True
            color = _color(tid)
            cx, cy = (x1+x2)//2, (y1+y2)//2
            if tid not in _trayectorias:
                _trayectorias[tid] = []
            cola = _trayectorias[tid]
            cola.append((cx, cy))
            if len(cola) > _MAX_PUNTOS:
                cola.pop(0)
            cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
            cv2.putText(frame, 'Persona #%d  %.2f' % (tid, conf),
                        (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)
            for i in range(1, len(cola)):
                g = max(1, int(3*i/len(cola)))
                cv2.line(frame, cola[i-1], cola[i], color, g, cv2.LINE_AA)
            tracks.append({'id': tid, 'bbox': (x1,y1,x2,y2), 'cx': cx, 'cy': cy, 'color': color})

    ids_activos = {t['id'] for t in tracks}
    obsoletos = [k for k in _trayectorias if k not in ids_activos]
    for k in obsoletos[:5]:
        del _trayectorias[k]

    return persona_detectada, tracks, frame
