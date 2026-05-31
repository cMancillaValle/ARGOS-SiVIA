from ultralytics import YOLO
import cv2

model = YOLO("runs/detect/train2/weights/best.pt")

def detectar_tarjeta(frame):
    results = model(frame, verbose=False)

    tarjeta_valida = False

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            if conf > 0.1:  # Reducido de 0.6 a 0.3 para que detecte al menos en algún momento
                if cls == 0:  # tuLlave
                    tarjeta_valida = True
                    label = "Valida"
                    color = (0,255,0)
                else:
                    label = "No valida"
                    color = (0,0,255)

                cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
                cv2.putText(frame, f"{label} {conf:.2f}",
                            (x1, y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            color,
                            2)

    return tarjeta_valida, frame