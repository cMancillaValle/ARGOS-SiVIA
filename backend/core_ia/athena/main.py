import cv2
from database.db import init_db

# Detectores
from detectors.person_detector import detectar_persona
from detectors.pose_detector import detectar_brazo
from detectors.hand_detector import detectar_mano
from detectors.card_detector import detectar_tarjeta

# Lógica
from logic.decision_engine import DecisionEngine

# Eventos
from events.event_manager import EventManager

# =========================
# INICIALIZACIÓN
# =========================
init_db()
engine = DecisionEngine()
cap = cv2.VideoCapture(0)
event_manager = EventManager()

# =========================
# LOOP PRINCIPAL
# =========================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Preprocesamiento
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # =========================
    # DETECTORES
    # =========================
    persona_detectada, frame = detectar_persona(frame)
    brazo_arriba, frame = detectar_brazo(frame, rgb)
    mano_estado, frame = detectar_mano(frame, rgb)
    tarjeta_detectada, frame = detectar_tarjeta(frame)

    # =========================
    # ESTADO GLOBAL
    # =========================
    estado = {
        "persona": persona_detectada,
        "brazo": brazo_arriba,
        "mano": mano_estado,
        "tarjeta": tarjeta_detectada
    }

    # =========================
    # EVENTOS SIMPLES
    # =========================
    eventos = event_manager.procesar_eventos(estado)

    # =========================
    # DECISIÓN
    # =========================
    evento_decision = engine.evaluar(estado)
    eventos_decision = event_manager.procesar_evento_decision(evento_decision)

    # =========================
    # DISPATCH
    # =========================
    event_manager.dispatch(eventos + eventos_decision)

    # =========================
    # VISUALIZACIÓN
    # =========================
    cv2.imshow("ARGOS - Sistema", frame)

    # ESC para salir
    if cv2.waitKey(1) & 0xFF == 27:
        break

# =========================
# CIERRE
# =========================
cap.release()
cv2.destroyAllWindows()