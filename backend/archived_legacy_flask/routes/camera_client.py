"""
routes/camera_client.py
──────────────────────────────────────────────────────────────────────────────
WebSocket endpoint para recibir frames de la cámara local del cliente
(navegador en otro PC).

Endpoints:
  WS  /api/camaras/client/push
      ← frames JPEG base64 del navegador

  GET /api/camaras/client/status
      ← estado de las conexiones

  GET /api/camaras/client/mjpeg?client_id=<id>
      ← stream MJPEG de un cliente específico

Protocolo WebSocket:

Cliente → Servidor:

Handshake:
{
    "token": "<token>",
    "cam_id": 1
}

Frame:
{
    "type": "frame",
    "data": "<base64-jpeg>",
    "ts": <unix-ms>
}

Ping:
{
    "type": "ping"
}

Servidor → Cliente:

{
    "type": "ok",
    "client_id": "<id>",
    "cam_id": 1
}

{
    "type": "pong"
}

{
    "type": "error",
    "message": "..."
}
"""

import base64
import json
import logging
import uuid
import time

from flask import Blueprint, request, jsonify, Response
from flask_sock import Sock


from services.auth_service import validate_token

logger = logging.getLogger(__name__)

camera_client_bp = Blueprint('camera_client', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# BUFFER
# ─────────────────────────────────────────────────────────────────────────────
def _get_client_buffer():
    """
    Obtiene el buffer compartido de clientes.
    """
    try:
        import sys
        import os

        backend_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__),
                '..'
            )
        )

        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        from core_ia.athena.client_frame_buffer import client_buffer

        return client_buffer

    except Exception as e:
        logger.error(
            f"No se pudo importar client_frame_buffer: {e}"
        )
        return None
    
# ─────────────────────────────────────────────────────────────────────────────
# MAPA CLIENTE → CÁMARA
# ─────────────────────────────────────────────────────────────────────────────

_client_cameras = {}


def get_client_camera(client_id):
    """
    Devuelve el cam_id asociado a un client_id.
    """
    return _client_cameras.get(client_id)


def get_client_by_camera(cam_id):
    """
    Devuelve el client_id del cliente activo que está transmitiendo para una cámara.
    """
    try:
        target_id = int(cam_id)
    except (ValueError, TypeError):
        return None

    buf = _get_client_buffer()
    active_clients = buf.clients() if buf else []

    for cid, c_id in list(_client_cameras.items()):
        try:
            if int(c_id) == target_id:
                if not active_clients or cid in active_clients:
                    return cid
        except (ValueError, TypeError):
            continue
    return None


def remove_client_camera(client_id):
    """
    Elimina la asociación cliente → cámara.
    """
    _client_cameras.pop(client_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

_sock_instance = None


def init_websocket(sock: Sock):
    """
    Registra el endpoint WebSocket en la instancia de Sock.
    """

    global _sock_instance
    _sock_instance = sock

    @sock.route('/api/camaras/client/push')
    def ws_client_push(ws):
        """
        WebSocket que recibe frames JPEG del navegador cliente.

        El primer mensaje debe contener:

        {
            "token": "...",
            "cam_id": 1
        }
        """

        client_id = str(uuid.uuid4())[:8]

        logger.info(
            f"[WS-Client {client_id}] Conexión entrante"
        )

        buf = _get_client_buffer()

        authenticated = False
        cam_id = None

        try:

            # ─────────────────────────────────────────────────────────────
            # HANDSHAKE
            # ─────────────────────────────────────────────────────────────

            raw = ws.receive(timeout=10)

            if not raw:
                ws.send(
                    json.dumps({
                        "type": "error",
                        "message": "Timeout handshake"
                    })
                )
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                ws.send(
                    json.dumps({
                        "type": "error",
                        "message": "Handshake inválido"
                    })
                )
                return

            token = msg.get("token", "")
            cam_id = msg.get("cam_id")

            # ─────────────────────────────────────────────────────────────
            # VALIDAR TOKEN
            # ─────────────────────────────────────────────────────────────

            if not validate_token(token):

                ws.send(
                    json.dumps({
                        "type": "error",
                        "message": "No autorizado"
                    })
                )

                logger.warning(
                    f"[WS-Client {client_id}] Token inválido"
                )

                return

            authenticated = True

            # ─────────────────────────────────────────────────────────────
            # VALIDAR CÁMARA
            # ─────────────────────────────────────────────────────────────

            if cam_id is None:

                ws.send(
                    json.dumps({
                        "type": "error",
                        "message": "cam_id requerido"
                    })
                )

                logger.warning(
                    f"[WS-Client {client_id}] cam_id no proporcionado"
                )

                return

            try:
                cam_id = int(cam_id)
            except (ValueError, TypeError):

                ws.send(
                    json.dumps({
                        "type": "error",
                        "message": "cam_id inválido"
                    })
                )

                return

            # ─────────────────────────────────────────────────────────────
            # ASOCIAR CLIENTE CON CÁMARA
            # ─────────────────────────────────────────────────────────────

            _client_cameras[client_id] = cam_id

            # ─────────────────────────────────────────────────────────────
            # RESPUESTA DE HANDSHAKE
            # ─────────────────────────────────────────────────────────────

            ws.send(
                json.dumps({
                    "type": "ok",
                    "client_id": client_id,
                    "cam_id": cam_id
                })
            )

            logger.info(
                f"[WS-Client {client_id}] "
                f"Autenticado ✓ → Cámara {cam_id}"
            )

            # ─────────────────────────────────────────────────────────────
            # RECIBIR FRAMES
            # ─────────────────────────────────────────────────────────────

            frame_count = 0
            last_log = time.time()

            while True:

                raw = ws.receive(timeout=30)

                if raw is None:
                    break

                try:

                    msg = json.loads(raw)

                    msg_type = msg.get("type", "")

                    # ─────────────────────────────────────────────────
                    # PING
                    # ─────────────────────────────────────────────────

                    if msg_type == "ping":

                        ws.send(
                            json.dumps({
                                "type": "pong"
                            })
                        )

                        continue

                    # ─────────────────────────────────────────────────
                    # FRAME
                    # ─────────────────────────────────────────────────

                    if msg_type == "frame":

                        b64_data = msg.get("data", "")

                        if not b64_data:
                            continue

                        # Eliminar prefijo:
                        # data:image/jpeg;base64,...
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]

                        try:
                            jpeg_bytes = base64.b64decode(
                                b64_data
                            )
                        except Exception as e:

                            logger.warning(
                                f"[WS-Client {client_id}] "
                                f"Base64 inválido: {e}"
                            )

                            continue

                        if not jpeg_bytes:
                            continue

                        # ─────────────────────────────────────────────
                        # GUARDAR FRAME
                        # ─────────────────────────────────────────────

                        if buf:

                            buf.write(
                                jpeg_bytes,
                                client_id=client_id
                            )

                        frame_count += 1

                        # ─────────────────────────────────────────────
                        # LOG CADA 10 SEGUNDOS
                        # ─────────────────────────────────────────────

                        now = time.time()

                        if now - last_log >= 10:

                            elapsed = now - last_log

                            fps = (
                                frame_count / elapsed
                                if elapsed > 0
                                else 0
                            )

                            logger.info(
                                f"[WS-Client {client_id}] "
                                f"Cámara {cam_id} → "
                                f"{frame_count} frames "
                                f"(~{fps:.1f} fps)"
                            )

                            frame_count = 0
                            last_log = now

                except json.JSONDecodeError:

                    logger.debug(
                        f"[WS-Client {client_id}] "
                        f"Mensaje no-JSON ignorado"
                    )

                except Exception as e:

                    logger.warning(
                        f"[WS-Client {client_id}] "
                        f"Error procesando frame: {e}"
                    )

        except Exception as e:

            logger.info(
                f"[WS-Client {client_id}] "
                f"Conexión cerrada: {e}"
            )

        finally:

            # ─────────────────────────────────────────────────────────────
            # LIMPIEZA
            # ─────────────────────────────────────────────────────────────

            if authenticated and buf:

                try:
                    buf.remove(client_id)
                except Exception as e:
                    logger.warning(
                        f"[WS-Client {client_id}] "
                        f"Error eliminando buffer: {e}"
                    )

            remove_client_camera(client_id)

            logger.info(
                f"[WS-Client {client_id}] "
                f"Desconectado "
                f"(Cámara {cam_id})"
            )


# ─────────────────────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────────────────────

@camera_client_bp.route('/client/status', methods=['GET'])
def client_status():
    """
    Devuelve el estado de todos los clientes conectados.
    """

    buf = _get_client_buffer()

    if not buf:

        return jsonify({
            "active": False,
            "clients": [],
            "error": "Buffer no disponible"
        })

    try:

        clients = buf.clients()

        result = []

        for client_id in clients:

            result.append({
                "client_id": client_id,
                "cam_id": get_client_camera(client_id)
            })

        return jsonify({
            "active": len(result) > 0,
            "count": len(result),
            "clients": result
        })

    except Exception as e:

        logger.error(
            f"Error obteniendo estado de clientes: {e}"
        )

        return jsonify({
            "active": False,
            "clients": [],
            "error": str(e)
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# MJPEG
# ─────────────────────────────────────────────────────────────────────────────

@camera_client_bp.route('/client/mjpeg', methods=['GET'])
def client_mjpeg():
    """
    Stream MJPEG de un cliente específico.

    Uso:

        /api/camaras/client/mjpeg?client_id=XXXXXXXX

    Esto permite que Athena consuma únicamente el stream
    correspondiente a una cámara.
    """

    buf = _get_client_buffer()

    client_id = request.args.get("client_id")

    if not client_id:

        return jsonify({
            "error": "client_id requerido"
        }), 400

    # Verificar que el cliente exista
    if not buf or client_id not in buf.clients():

        return jsonify({
            "error": "Cliente no conectado",
            "client_id": client_id
        }), 404

    def generate():

        boundary = (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n"
        )

        last_frame = None

        while True:

            try:

                if not buf:
                    time.sleep(0.1)
                    continue

                frame_bytes = buf.read(client_id)

                if frame_bytes:

                    # Evitar enviar exactamente el mismo frame
                    # repetidamente mientras llega uno nuevo.
                    if frame_bytes != last_frame:

                        last_frame = frame_bytes

                        yield (
                            boundary
                            + frame_bytes
                            + b"\r\n"
                        )

                else:

                    # El cliente ya no tiene frame.
                    if client_id not in buf.clients():
                        break

                    time.sleep(0.05)

            except GeneratorExit:
                break

            except Exception as e:

                logger.warning(
                    f"[MJPEG {client_id}] "
                    f"Error: {e}"
                )

                break

    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )