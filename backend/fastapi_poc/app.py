"""
backend/fastapi_poc/app.py
──────────────────────────────────────────────────────────────────────────────
Servidor FastAPI independiente (PoC) para el WebSocket de ingesta de cámaras:
    WS /api/camaras/client/push

Replica fielmente el protocolo y comportamiento de backend/routes/camera_client.py
utilizando FastAPI y Uvicorn sobre entorno asíncrono, reutilizando los servicios
existentes de autenticación y el buffer de frames en memoria.

Protocolo WebSocket:

Cliente → Servidor:
  1. Handshake inicial:
     {
         "token": "<token-sesion>",
         "cam_id": 1
     }

  2. Frames:
     {
         "type": "frame",
         "data": "<jpeg-en-base64>",
         "ts": <unix-ms>
     }

  3. Ping:
     {
         "type": "ping"
     }

Servidor → Cliente:
  - OK Handshake: {"type": "ok", "client_id": "<id>", "cam_id": 1}
  - Pong:         {"type": "pong"}
  - Error:        {"type": "error", "message": "<motivo>"}
──────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import uuid
import time
import base64
import asyncio
import logging
from typing import Optional, Dict

# Asegurar que la carpeta 'backend' esté en sys.path para reutilizar módulos existentes
BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

# Reutilizar servicios y buffer existentes de ARGOS-SiViA
from services.auth_service import validate_token
from core_ia.athena.client_frame_buffer import client_buffer

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fastapi_poc.camera_ws")

app = FastAPI(
    title="ARGOS-SiViA - Camera WebSocket PoC (FastAPI)",
    description="Servidor de prueba aislado para WebSocket de cámaras",
    version="1.0.0"
)

# ─────────────────────────────────────────────────────────────────────────────
# MAPA CLIENTE → CÁMARA (Memoria local en el proceso FastAPI)
# ─────────────────────────────────────────────────────────────────────────────
_client_cameras: Dict[str, int] = {}


def get_client_camera(client_id: str) -> Optional[int]:
    """Devuelve el cam_id asociado a un client_id."""
    return _client_cameras.get(client_id)


def get_client_by_camera(cam_id: int) -> Optional[str]:
    """Devuelve el client_id activo para una cámara dada."""
    try:
        target_id = int(cam_id)
    except (ValueError, TypeError):
        return None

    active_clients = client_buffer.clients() if client_buffer else []
    for cid, c_id in list(_client_cameras.items()):
        try:
            if int(c_id) == target_id:
                if not active_clients or cid in active_clients:
                    return cid
        except (ValueError, TypeError):
            continue
    return None


def remove_client_camera(client_id: str):
    """Elimina la asociación cliente → cámara."""
    _client_cameras.pop(client_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────
@app.websocket("/api/camaras/client/push")
async def ws_client_push(websocket: WebSocket):
    """
    WebSocket que recibe frames JPEG del cliente / navegador remoto.
    """
    await websocket.accept()

    client_id = str(uuid.uuid4())[:8]
    logger.info(f"[WS-FastAPI {client_id}] Conexión entrante")

    authenticated = False
    cam_id = None

    try:
        # ─────────────────────────────────────────────────────────────────────
        # 1. HANDSHAKE (Timeout 10 segundos)
        # ─────────────────────────────────────────────────────────────────────
        try:
            raw_data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"[WS-FastAPI {client_id}] Timeout esperando handshake (10s)")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Timeout handshake"
            }))
            await websocket.close()
            return

        try:
            msg = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[WS-FastAPI {client_id}] Mensaje de handshake no es JSON válido")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Handshake inválido"
            }))
            await websocket.close()
            return

        token = msg.get("token", "")
        raw_cam_id = msg.get("cam_id")

        # ─────────────────────────────────────────────────────────────────────
        # 2. VALIDAR TOKEN
        # ─────────────────────────────────────────────────────────────────────
        if not validate_token(token):
            logger.warning(f"[WS-FastAPI {client_id}] Token inválido o expirado")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "No autorizado"
            }))
            await websocket.close()
            return

        authenticated = True

        # ─────────────────────────────────────────────────────────────────────
        # 3. VALIDAR CÁMARA
        # ─────────────────────────────────────────────────────────────────────
        if raw_cam_id is None:
            logger.warning(f"[WS-FastAPI {client_id}] cam_id no proporcionado")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "cam_id requerido"
            }))
            await websocket.close()
            return

        try:
            cam_id = int(raw_cam_id)
        except (ValueError, TypeError):
            logger.warning(f"[WS-FastAPI {client_id}] cam_id inválido: {raw_cam_id}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "cam_id inválido"
            }))
            await websocket.close()
            return

        # Asociar cliente con cámara
        _client_cameras[client_id] = cam_id

        # Responder confirmación de handshake exitoso
        await websocket.send_text(json.dumps({
            "type": "ok",
            "client_id": client_id,
            "cam_id": cam_id
        }))
        logger.info(f"[WS-FastAPI {client_id}] Autenticado ✓ → Cámara {cam_id}")

        # ─────────────────────────────────────────────────────────────────────
        # 4. BUCLE DE RECEPCIÓN DE MENSAJES / FRAMES
        # ─────────────────────────────────────────────────────────────────────
        frame_count = 0
        last_log = time.time()

        while True:
            # Esperar el siguiente mensaje (timeout de inactividad de 30 segundos)
            try:
                raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.info(f"[WS-FastAPI {client_id}] Desconexión por timeout de inactividad (30s)")
                break

            try:
                payload = json.loads(raw_msg)
            except json.JSONDecodeError:
                logger.debug(f"[WS-FastAPI {client_id}] Mensaje no-JSON ignorado")
                continue

            msg_type = payload.get("type", "")

            # ── PING / PONG ──
            if msg_type == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong"
                }))
                continue

            # ── FRAME JPEG ──
            if msg_type == "frame":
                b64_data = payload.get("data", "")
                if not b64_data:
                    continue

                # Remover prefijo data URL si viene presente (ej. data:image/jpeg;base64,...)
                if "," in b64_data:
                    b64_data = b64_data.split(",", 1)[1]

                try:
                    jpeg_bytes = base64.b64decode(b64_data)
                except Exception as e:
                    logger.warning(f"[WS-FastAPI {client_id}] Error decodificando Base64: {e}")
                    continue

                if not jpeg_bytes:
                    continue

                # Escribir frame en el buffer compartido de Athena
                if client_buffer:
                    client_buffer.write(jpeg_bytes, client_id=client_id)

                frame_count += 1

                # Métricas / Log periódico cada 10 segundos
                now = time.time()
                if now - last_log >= 10.0:
                    elapsed = now - last_log
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"[WS-FastAPI {client_id}] Cámara {cam_id} → {frame_count} frames (~{fps:.1f} fps)"
                    )
                    frame_count = 0
                    last_log = now

    except WebSocketDisconnect:
        logger.info(f"[WS-FastAPI {client_id}] Conexión cerrada por el cliente (WebSocketDisconnect)")
    except Exception as e:
        logger.info(f"[WS-FastAPI {client_id}] Conexión cerrada con excepción: {e}")
    finally:
        # ─────────────────────────────────────────────────────────────────────
        # 5. LIMPIEZA
        # ─────────────────────────────────────────────────────────────────────
        if authenticated and client_buffer:
            try:
                client_buffer.remove(client_id)
            except Exception as e:
                logger.warning(f"[WS-FastAPI {client_id}] Error removiendo del buffer: {e}")

        remove_client_camera(client_id)
        logger.info(f"[WS-FastAPI {client_id}] Desconectado (Cámara {cam_id})")


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS AUXILIARES DE DIAGNÓSTICO (Solo lectura)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Endpoint HTTP simple para verificar que el servidor FastAPI está arriba."""
    return {"status": "ok", "service": "fastapi_camera_ws_poc", "port": 8001}


@app.get("/api/camaras/client/status")
async def client_status():
    """Devuelve el estado actual de los clientes conectados al servidor FastAPI."""
    if not client_buffer:
        return JSONResponse(status_code=500, content={"active": False, "clients": [], "error": "Buffer no disponible"})

    try:
        clients = client_buffer.clients()
        result = [
            {"client_id": cid, "cam_id": get_client_camera(cid)}
            for cid in clients
        ]
        return {
            "active": len(result) > 0,
            "count": len(result),
            "clients": result
        }
    except Exception as e:
        logger.error(f"Error consultando estado: {e}")
        return JSONResponse(status_code=500, content={"active": False, "clients": [], "error": str(e)})
