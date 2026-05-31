from ultralytics import YOLO
import cv2

model = YOLO("yolov8n.pt")

def detectar_persona(frame):
    results = model(frame, verbose=False)
    persona_detectada = False

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            
            # Solo pintamos si hay buena confianza
            if conf > 0.3:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # Clase 0: Persona
                if cls == 0:
                    persona_detectada = True
                    cv2.rectangle(frame, (x1,y1), (x2,y2), (255,0,0), 2)
                    cv2.putText(frame, f"Persona {conf:.2f}", (x1, y1-10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,0,0), 2)

    return persona_detectada, frame