"""
detectors/hand_detector.py
──────────────────────────────────────────────────────────────────
Detector de manos con visualización mejorada de 21 puntos por mano.
Usa MediaPipe Hands con calidad alta (min_detection_confidence 0.7).
Pinta cada dedo con un color distinto y distingue falanges.
"""

import mediapipe as mp
import cv2

# ── Configuración robusta ───────────────────────────────────────────────────
mp_hands    = mp.solutions.hands
mp_draw     = mp.solutions.drawing_utils
mp_draw_styles = mp.solutions.drawing_styles

# max_num_hands=1 y model_complexity=0 para máxima velocidad en tiempo real
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=0,           # 0=ligero (Lite, ultrarrápido), 1=completo
    min_detection_confidence=0.60,
    min_tracking_confidence=0.55,
)

# ── Colores por dedo (BGR) ──────────────────────────────────────────────────
FINGER_COLORS = {
    "pulgar":   (0,   200, 255),   # Amarillo-naranja
    "indice":   (0,   255,  80),   # Verde
    "medio":    (255, 120,   0),   # Azul
    "anular":   (200,   0, 255),   # Violeta
    "meñique":  (0,   100, 255),   # Rojo-naranja
}

# Índices de puntos por dedo: [base, medio, punta]
FINGER_LANDMARKS = {
    "pulgar":  [2, 3, 4],
    "indice":  [5, 6, 7, 8],
    "medio":   [9, 10, 11, 12],
    "anular":  [13, 14, 15, 16],
    "meñique": [17, 18, 19, 20],
}

# Tips IDs para lógica de abierto/cerrado
TIPS_IDS = [4, 8, 12, 16, 20]


def _draw_hand_custom(frame, hand_landmarks, h, w):
    """Dibuja conexiones y puntos con colores por dedo."""
    lm = hand_landmarks.landmark

    fingers_to_lm = [
        ("pulgar",  [2, 3, 4]),
        ("indice",  [5, 6, 7, 8]),
        ("medio",   [9, 10, 11, 12]),
        ("anular",  [13, 14, 15, 16]),
        ("meñique", [17, 18, 19, 20]),
    ]

    # Dibujar palma (puntos 0–5–9–13–17–0)
    palm_ids = [0, 5, 9, 13, 17, 0]
    palm_pts = []
    for pid in palm_ids:
        px = int(lm[pid].x * w)
        py = int(lm[pid].y * h)
        palm_pts.append((px, py))
    for i in range(len(palm_pts) - 1):
        cv2.line(frame, palm_pts[i], palm_pts[i+1], (180, 180, 180), 1)

    # Dibujar cada dedo con su color
    for name, ids in fingers_to_lm:
        color = FINGER_COLORS[name]
        pts = [(int(lm[i].x * w), int(lm[i].y * h)) for i in ids]
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i+1], color, 2)
        for j, pt in enumerate(pts):
            radius = 5 if j == len(pts) - 1 else 3   # punta más grande
            cv2.circle(frame, pt, radius, color, -1)
            cv2.circle(frame, pt, radius + 1, (255, 255, 255), 1)

    # Punto de muñeca
    wx = int(lm[0].x * w)
    wy = int(lm[0].y * h)
    cv2.circle(frame, (wx, wy), 6, (255, 255, 255), -1)
    cv2.circle(frame, (wx, wy), 7, (100, 100, 100), 1)


def detectar_mano(frame, rgb):
    results = hands.process(rgb)
    mano_estado = ""

    if results.multi_hand_landmarks:
        h, w = frame.shape[:2]
        for hand_landmarks in results.multi_hand_landmarks:
            # Dibujo personalizado de alta calidad
            _draw_hand_custom(frame, hand_landmarks, h, w)

            lm = hand_landmarks.landmark

            # ── Clasificación gesto ─────────────────────────────────────────
            fingers = []
            # Pulgar: comparar eje X
            if lm[4].x < lm[3].x:
                fingers.append(1)
            else:
                fingers.append(0)
            # Resto de dedos: punta más alta que la falange siguiente
            for i in range(1, 5):
                if lm[TIPS_IDS[i]].y < lm[TIPS_IDS[i] - 2].y:
                    fingers.append(1)
                else:
                    fingers.append(0)

            total = sum(fingers)
            if total == 0:
                mano_estado = "cerrada"
            elif total == 5:
                mano_estado = "abierta"
            else:
                mano_estado = "gesto"

            # Etiqueta del gesto sobre la muñeca
            wx = int(lm[0].x * w)
            wy = int(lm[0].y * h)
            label = f"Mano: {mano_estado} ({total}/5)"
            cv2.putText(frame, label, (wx - 30, wy + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1, cv2.LINE_AA)

    return mano_estado, frame