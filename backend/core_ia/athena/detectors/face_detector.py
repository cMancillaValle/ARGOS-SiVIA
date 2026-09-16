"""
detectors/face_detector.py
──────────────────────────────────────────────────────────────────
Detección de rostro con MediaPipe FaceMesh — 468 puntos en 3D.
Dibuja el contorno facial completo: cejas, ojos, nariz, labios,
mandíbula y cuadrícula de la malla completa.
"""

import mediapipe as mp
import cv2

# ── Setup MediaPipe FaceMesh ─────────────────────────────────────────────────
mp_face_mesh  = mp.solutions.face_mesh
mp_draw       = mp.solutions.drawing_utils
mp_draw_styles = mp.solutions.drawing_styles

face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=2,
    refine_landmarks=True,         # 478 puntos: +10 en iris/pupilas
    min_detection_confidence=0.65,
    min_tracking_confidence=0.60,
)

# ── Estilos de dibujo personalizados ─────────────────────────────────────────
_TESSELATION_SPEC = mp_draw.DrawingSpec(color=(80, 80, 80), thickness=1, circle_radius=0)
_CONTOUR_SPEC     = mp_draw.DrawingSpec(color=(0, 200, 255), thickness=1, circle_radius=1)
_IRIS_SPEC        = mp_draw.DrawingSpec(color=(0, 255, 120), thickness=1, circle_radius=1)

# Índices de contornos importantes (FaceMesh)
_FACE_OVAL_IDX  = list(mp_face_mesh.FACEMESH_FACE_OVAL)
_LEFT_EYE_IDX   = list(mp_face_mesh.FACEMESH_LEFT_EYE)
_RIGHT_EYE_IDX  = list(mp_face_mesh.FACEMESH_RIGHT_EYE)
_LIPS_IDX       = list(mp_face_mesh.FACEMESH_LIPS)
_L_EYEBROW_IDX  = list(mp_face_mesh.FACEMESH_LEFT_EYEBROW)
_R_EYEBROW_IDX  = list(mp_face_mesh.FACEMESH_RIGHT_EYEBROW)
_NOSE_IDX       = list(mp_face_mesh.FACEMESH_NOSE)


def _draw_connections(frame, landmarks, connection_list, spec, h, w):
    for conn in connection_list:
        start_idx, end_idx = conn
        s = landmarks[start_idx]
        e = landmarks[end_idx]
        sx, sy = int(s.x * w), int(s.y * h)
        ex, ey = int(e.x * w), int(e.y * h)
        cv2.line(frame, (sx, sy), (ex, ey), spec.color, spec.thickness, cv2.LINE_AA)


def detectar_rostro(frame, rgb):
    """
    Detecta rostros y dibuja la malla completa de 478 puntos.
    Retorna (rostro_detectado: bool, frame_anotado).
    """
    results = face_mesh.process(rgb)
    rostro_detectado = False

    if results.multi_face_landmarks:
        h, w = frame.shape[:2]
        for face_lms in results.multi_face_landmarks:
            rostro_detectado = True
            lms = face_lms.landmark

            # 1. Cuadrícula de tesselación (malla gris sutil)
            mp_draw.draw_landmarks(
                frame,
                face_lms,
                mp_face_mesh.FACEMESH_TESSELATION,
                landmark_drawing_spec=None,
                connection_drawing_spec=_TESSELATION_SPEC,
            )

            # 2. Contornos principales en cyan brillante
            for conn_set in (_FACE_OVAL_IDX, _LEFT_EYE_IDX, _RIGHT_EYE_IDX,
                              _LIPS_IDX, _L_EYEBROW_IDX, _R_EYEBROW_IDX):
                _draw_connections(frame, lms, conn_set, _CONTOUR_SPEC, h, w)

            # 3. Iris (verde brillante) — solo si refine_landmarks=True
            try:
                for conn_set in (mp_face_mesh.FACEMESH_LEFT_IRIS, mp_face_mesh.FACEMESH_RIGHT_IRIS):
                    _draw_connections(frame, lms, conn_set, _IRIS_SPEC, h, w)
            except Exception:
                pass

            # 4. Puntos clave en los ojos
            for idx in [33, 263, 1, 61, 291, 199, 4]:   # nariz, ojos, barbilla
                lm = lms[idx]
                px, py = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (px, py), 2, (0, 200, 255), -1)

    return rostro_detectado, frame
