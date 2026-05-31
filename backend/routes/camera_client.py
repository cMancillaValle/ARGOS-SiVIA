"""
routes/camera_client.py
──────────────────────────────────────────────────────────────────────────────
WebSocket endpoint para recibir frames de la cámara local del cliente
(navegador en otro PC).

Endpoints:
  WS  /api/camaras/client/push    ← frames JPEG base64 del navegador
  GET /api/camaras/client/status  ← estado de la conexión cliente

Protocolo WebSocket (texto JSON):
  Cliente → Servidor:
    { "type": "frame", "data": "<base64-jpeg>", "ts": <unix-ms> }
    { "type": "ping" }

  Servidor → Cliente:
    { "type": "pong" }
    { "type": "error", "message": "..." }
    { "type": "ok" }
"""

import base64
import json
import logging
import uuid
import time

from flask import Blueprint, request, jsonify
from flask_sock import Sock

from services.auth_service import validate_token

logger = logging.getLogger(__name__)

camera_client_bp = Blueprint('camera_client', __name__)

# Importar buffer global
def _get_client_buffer():
    try:
        import sys, os
        athena_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', 'core_ia', 'athena')
        )
        if athena_dir not in sys.path:
            sys.path.insert(0, athena_dir)
        from client_frame_buffer import client_buffer
        return client_buffer
    except Exception as e:
        logger.error(f"No se pudo importar client_frame_buffer: {e}")
        return None


# ── WebSocket: recibir frames del cliente ────────────────────────────────────
# Nota: sock se inyecta desde app.py al registrar el blueprint
_sock_instance = None

def init_websocket(sock: Sock):
    """Registra el endpoint WebSocket en la instancia de Sock."""
    global _sock_instance
    _sock_instance = sock

    @sock.route('/api/camaras/client/push')
    def ws_client_push(ws):
        """
        WebSocket que recibe frames JPEG del navegador cliente.
        Autenticación via primer mensaje de handshake con token.
        """
        client_id = str(uuid.uuid4())[:8]
        logger.info(f"[WS-Client {client_id}] Conexión entrante")

        buf = _get_client_buffer()
        authenticated = False

        try:
            # Primer mensaje debe ser handshake con token
            raw = ws.receive(timeout=10)
            if not raw:
                ws.send(json.dumps({"type": "error", "message": "Timeout handshake"}))
                return

            msg = json.loads(raw)
            token = msg.get("token", "")
            if not validate_token(token):
                ws.send(json.dumps({"type": "error", "message": "No autorizado"}))
                logger.warning(f"[WS-Client {client_id}] Token inválido")
                return

            authenticated = True
            ws.send(json.dumps({"type": "ok", "client_id": client_id}))
            logger.info(f"[WS-Client {client_id}] Autenticado ✓")

            # Loop principal: recibir frames
            frame_count = 0
            last_log = time.time()

            while True:
                raw = ws.receive(timeout=30)
                if raw is None:
                    break  # cliente desconectó

                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")

                    if msg_type == "ping":
                        ws.send(json.dumps({"type": "pong"}))
                        continue

                    if msg_type == "frame":
                        b64_data = msg.get("data", "")
                        # Puede venir con o sin prefijo data:image/jpeg;base64,
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]

                        jpeg_bytes = base64.b64decode(b64_data)

                        if buf:
                            buf.write(jpeg_bytes, client_id=client_id)

                        frame_count += 1
                        now = time.time()
                        if now - last_log >= 10:
                            fps = frame_count / (now - last_log) if (now - last_log) > 0 else 0
                            logger.info(
                                f"[WS-Client {client_id}] {frame_count} frames recibidos "
                                f"(~{fps:.1f} fps efectivos)"
                            )
                            frame_count = 0
                            last_log = now

                except json.JSONDecodeError:
                    logger.debug(f"[WS-Client {client_id}] Mensaje no-JSON ignorado")
                except Exception as e:
                    logger.warning(f"[WS-Client {client_id}] Error procesando frame: {e}")

        except Exception as e:
            logger.info(f"[WS-Client {client_id}] Conexión cerrada: {e}")
        finally:
            if buf and authenticated:
                buf.disconnect()
            logger.info(f"[WS-Client {client_id}] Desconectado")


# ── GET /api/camaras/client/status ───────────────────────────────────────────
@camera_client_bp.route('/client/status', methods=['GET'])
def client_status():
    """Estado actual de la conexión webcam cliente."""
    buf = _get_client_buffer()
    if not buf:
        return jsonify({"active": False, "error": "Buffer no disponible"})
    return jsonify(buf.status())


# ── GET /api/camaras/client/mjpeg ────────────────────────────────────────────
@camera_client_bp.route('/client/mjpeg', methods=['GET'])
def client_mjpeg():
    """Endpoint interno (MJPEG) para que 'athena_worker.py' pueda leer los frames de la webcam remota como si fuera un RTSP."""
    from flask import Response
    buf = _get_client_buffer()

    def generate():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        last_ts = -1.0
        while True:
            # Esperar a que el navegador envíe el siguiente frame
            if buf:
                buf.wait_for_new(timeout=0.1)
                frame_bytes, ts = buf.read_with_ts()
                if frame_bytes and ts != last_ts:
                    last_ts = ts
                    yield boundary + frame_bytes + b"\r\n"
            else:
                time.sleep(0.1)

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')
