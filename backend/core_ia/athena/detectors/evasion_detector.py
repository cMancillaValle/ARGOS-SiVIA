import cv2
import time

try:
    import mediapipe as mp
    _mp_pose = mp.solutions.pose
    _pose_model = _mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        min_detection_confidence=0.45,
        min_tracking_confidence=0.45,
    )
    POSE_DISPONIBLE = True
except Exception:
    POSE_DISPONIBLE = False


class EvasionDetector:
    def __init__(self, tripwire_y_ratio=0.55, cooldown=4.0):
        self.tripwire_ratio = tripwire_y_ratio
        self.cooldown = cooldown
        self._hip_history = {}
        self._last_alerta = {}
        self._lado_anterior = {}

    def _en_cooldown(self, tid):
        return (time.time() - self._last_alerta.get(tid, 0.0)) < self.cooldown

    def _registrar_alerta(self, tid):
        self._last_alerta[tid] = time.time()

    def _analizar_pose(self, frame, rgb, bbox):
        if not POSE_DISPONIBLE:
            return 'normal'
        x1, y1, x2, y2 = bbox
        h_f, w_f = frame.shape[:2]
        pad = 10
        rx1, ry1 = max(0,x1-pad), max(0,y1-pad)
        rx2, ry2 = min(w_f,x2+pad), min(h_f,y2+pad)
        roi = rgb[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            return 'normal'
        res = _pose_model.process(roi)
        if not res.pose_landmarks:
            return 'normal'
        lm = res.pose_landmarks.landmark
        L  = _mp_pose.PoseLandmark
        sh_l = lm[L.LEFT_SHOULDER];  sh_r = lm[L.RIGHT_SHOULDER]
        hi_l = lm[L.LEFT_HIP];       hi_r = lm[L.RIGHT_HIP]
        kn_l = lm[L.LEFT_KNEE];      kn_r = lm[L.RIGHT_KNEE]
        nose = lm[L.NOSE]
        mid_sh_y  = (sh_l.y + sh_r.y) / 2
        mid_hi_y  = (hi_l.y + hi_r.y) / 2
        mid_kn_y  = (kn_l.y + kn_r.y) / 2
        torso_h   = mid_hi_y - mid_sh_y
        if torso_h < 0.05:
            return 'normal'
        if mid_kn_y < mid_hi_y - torso_h * 0.3:
            return 'salto'
        if nose.y > mid_hi_y - torso_h * 0.1:
            return 'agachado'
        return 'normal'

    def analizar(self, tracks, frame, rgb):
        h, w = frame.shape[:2]
        tw_y = int(h * self.tripwire_ratio)
        cv2.line(frame, (0, tw_y), (w, tw_y), (0,100,255), 1)
        cv2.putText(frame, 'ZONA TORNIQUETE', (5, tw_y-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,100,255), 1, cv2.LINE_AA)
        alertas = []
        for track in tracks:
            tid  = track['id']
            cy   = track['cy']
            bbox = track['bbox']
            if self._en_cooldown(tid):
                continue
            lado_actual = 'abajo' if cy > tw_y else 'arriba'
            lado_prev   = self._lado_anterior.get(tid, lado_actual)
            cruce = (lado_prev == 'arriba' and lado_actual == 'abajo')
            self._lado_anterior[tid] = lado_actual
            if not cruce:
                continue
            pose_r = self._analizar_pose(frame, rgb, bbox)
            if pose_r == 'salto':
                subtipo = 'salto'
                desc = 'Salto de torniquete detectado (Persona #%d)' % tid
            elif pose_r == 'agachado':
                subtipo = 'agachado'
                desc = 'Paso por debajo del torniquete (Persona #%d)' % tid
            else:
                subtipo = 'cruce'
                desc = 'Cruce no autorizado (Persona #%d)' % tid
            self._registrar_alerta(tid)
            x1, y1, x2, y2 = bbox
            cv2.rectangle(frame, (x1,y1), (x2,y2), (0,0,255), 3)
            cv2.putText(frame, 'EVASION #%d' % tid, (x1, y1-22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2, cv2.LINE_AA)
            cv2.putText(frame, subtipo.upper(), (x1, y1-6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,60,255), 1, cv2.LINE_AA)
            alertas.append({
                'tipo':        'EVASION_DETECTADA',
                'subtipo':     subtipo,
                'track_id':    tid,
                'descripcion': desc,
                'ts':          time.time(),
            })
        return alertas
