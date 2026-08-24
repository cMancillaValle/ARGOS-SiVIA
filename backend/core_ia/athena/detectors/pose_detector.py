import mediapipe as mp
import cv2

mp_pose = mp.solutions.pose
mp_draw = mp.solutions.drawing_utils

pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=0,           # 0=Lite (ultrarrápido en CPU), 1=Full
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

def detectar_brazo(frame, rgb):
    results = pose.process(rgb)
    brazo_arriba = False

    if results.pose_landmarks:
        mp_draw.draw_landmarks(
            frame,
            results.pose_landmarks,
            mp_pose.POSE_CONNECTIONS
        )

        landmarks = results.pose_landmarks.landmark

        # Puntos clave para brazo
        shoulder_r = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
        wrist_r = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST]

        if wrist_r.y < shoulder_r.y:
            brazo_arriba = True

        # Puntos clave para agacharse (anomalía)
        nose = landmarks[mp_pose.PoseLandmark.NOSE]
        left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
        left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP]
        right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP]
        left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE]
        right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE]

        # Promedios en Y (altura)
        mid_shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
        mid_hip_y = (left_hip.y + right_hip.y) / 2
        mid_knee_y = (left_knee.y + right_knee.y) / 2

        # Altura del torso como referencia
        torso_y = mid_hip_y - mid_shoulder_y

        # Evitar divisiones por cero o cálculos extraños si torso_y es muy bajo o negativo
        if torso_y > 0.05:
            # 1. ¿Cabeza baja mucho respecto a la cadera? (Ej: Inclinarse hacia adelante)
            cabeza_baja = (mid_hip_y - nose.y) < (torso_y * 0.4)

            # 2. ¿Rodillas suben mucho respecto a la cadera? (Ej: Ponerse en cuclillas / agacharse)
            dist_cadera_rodilla = mid_knee_y - mid_hip_y
            
            # Solo evaluar rodillas si están medianamente visibles
            rodillas_visibles = (left_knee.visibility > 0.5 or right_knee.visibility > 0.5)
            rodillas_suben = False
            if rodillas_visibles:
                rodillas_suben = dist_cadera_rodilla < (torso_y * 0.5)

            # Si detectamos anomalía geométrica, lo ponemos en consola
            if cabeza_baja or rodillas_suben:
                print("🚨 ALERTA: Posición anómala detectada (Agachado/Inclinado)")
                # (Opcional) pintarlo en pantalla
                cv2.putText(frame, "Alerta: Agachado", (30, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

    return brazo_arriba, frame