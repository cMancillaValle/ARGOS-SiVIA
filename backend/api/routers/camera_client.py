"""
api/routers/camera_client.py
──────────────────────────────────────────────────────────────────────────────
WebSocket endpoint y streaming para recibir frames de cámara cliente / navegador.

Endpoints:
  WS  /api/camaras/client/push   ← Frames JPEG base64 del navegador remoto
  GET /api/camaras/client/status ← Estado de las conexiones cliente
  GET /api/camaras/client/mjpeg  ← Stream MJPEG de un cliente específico

Mantiene el mismo protocolo exacto y memoria compartida con Athena:
  core_ia.athena.client_frame_buffer.client_buffer
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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

# Reutilizar servicios y buffer existentes
from services.auth_service import validate_token
from core_ia.athena.client_frame_buffer import client_buffer

logger = logging.getLogger(__name__)
router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# MAPA CLIENTE → CÁMARA (Memoria local en el proceso único)
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
# WEBSOCKET /api/camaras/client/push
# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/client/push")
async def ws_client_push(websocket: WebSocket):
    """
    WebSocket que recibe frames JPEG del cliente / navegador remoto.
    Ruta montada bajo /api/camaras → /api/camaras/client/push
    """
    await websocket.accept()

    client_id = str(uuid.uuid4())[:8]
    logger.info(f"[WS-Client {client_id}] Conexión entrante")

    authenticated = False
    cam_id = None

    try:
        # ─────────────────────────────────────────────────────────────────────
        # 1. HANDSHAKE (Timeout 10 segundos)
        # ─────────────────────────────────────────────────────────────────────
        try:
            raw_data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"[WS-Client {client_id}] Timeout esperando handshake (10s)")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Timeout handshake"
            }))
            await websocket.close()
            return

        try:
            msg = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"[WS-Client {client_id}] Mensaje de handshake no es JSON válido")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Handshake inválido"
            }))
            await websocket.close()
            return

        token = msg.get("token", "")
        raw_cam_id = msg.get("cam_id")

        # ─────────────────────────────────────────────────────────────────────
        # 2. VALIDAR TOKEN (Operación de BD delegada a run_in_threadpool)
        # ─────────────────────────────────────────────────────────────────────
        user = await run_in_threadpool(validate_token, token)
        if not user:
            logger.warning(f"[WS-Client {client_id}] Token inválido o expirado")
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
            logger.warning(f"[WS-Client {client_id}] cam_id no proporcionado")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "cam_id requerido"
            }))
            await websocket.close()
            return

        try:
            cam_id = int(raw_cam_id)
        except (ValueError, TypeError):
            logger.warning(f"[WS-Client {client_id}] cam_id inválido: {raw_cam_id}")
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
        logger.info(f"[WS-Client {client_id}] Autenticado ✓ → Cámara {cam_id}")

        # ─────────────────────────────────────────────────────────────────────
        # 4. BUCLE DE RECEPCIÓN DE MENSAJES / FRAMES
        # ─────────────────────────────────────────────────────────────────────
        frame_count = 0
        last_log = time.time()

        while True:
            try:
                raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.info(f"[WS-Client {client_id}] Desconexión por timeout de inactividad (30s)")
                break

            try:
                payload = json.loads(raw_msg)
            except json.JSONDecodeError:
                logger.debug(f"[WS-Client {client_id}] Mensaje no-JSON ignorado")
                continue

            msg_type = payload.get("type", "")

            # ── PING / PONG ──
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            # ── FRAME JPEG ──
            if msg_type == "frame":
                b64_data = payload.get("data", "")
                if not b64_data:
                    continue

                if "," in b64_data:
                    b64_data = b64_data.split(",", 1)[1]

                try:
                    jpeg_bytes = base64.b64decode(b64_data)
                except Exception as e:
                    logger.warning(f"[WS-Client {client_id}] Error decodificando Base64: {e}")
                    continue

                if not jpeg_bytes:
                    continue

                if client_buffer:
                    client_buffer.write(jpeg_bytes, client_id=client_id)

                frame_count += 1

                now = time.time()
                if now - last_log >= 10.0:
                    elapsed = now - last_log
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    logger.info(
                        f"[WS-Client {client_id}] Cámara {cam_id} → {frame_count} frames (~{fps:.1f} fps)"
                    )
                    frame_count = 0
                    last_log = now

    except WebSocketDisconnect:
        logger.info(f"[WS-Client {client_id}] Conexión cerrada por el cliente")
    except Exception as e:
        logger.info(f"[WS-Client {client_id}] Conexión cerrada: {e}")
    finally:
        # ─────────────────────────────────────────────────────────────────────
        # 5. LIMPIEZA
        # ─────────────────────────────────────────────────────────────────────
        if authenticated and client_buffer:
            try:
                client_buffer.remove(client_id)
            except Exception as e:
                logger.warning(f"[WS-Client {client_id}] Error removiendo del buffer: {e}")

        remove_client_camera(client_id)
        logger.info(f"[WS-Client {client_id}] Desconectado (Cámara {cam_id})")


# ─────────────────────────────────────────────────────────────────────────────
# STATUS & MJPEG
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/client/status")
def client_status():
    """Devuelve el estado de todos los clientes conectados."""
    if not client_buffer:
        return JSONResponse(content={
            "active": False,
            "clients": [],
            "error": "Buffer no disponible"
        })

    try:
        clients = client_buffer.clients()
        result = []
        for cid in clients:
            result.append({
                "client_id": cid,
                "cam_id": get_client_camera(cid)
            })

        return JSONResponse(content={
            "active": len(result) > 0,
            "count": len(result),
            "clients": result
        })
    except Exception as e:
        logger.error(f"Error obteniendo estado de clientes: {e}")
        return JSONResponse(status_code=500, content={
            "active": False,
            "clients": [],
            "error": str(e)
        })


@router.get("/client/mjpeg")
def client_mjpeg(client_id: Optional[str] = None):
    """
    Stream MJPEG de un cliente específico.
    /api/camaras/client/mjpeg?client_id=XXXXXXXX
    """
    if not client_id:
        return JSONResponse(status_code=400, content={"error": "client_id requerido"})

    if not client_buffer or client_id not in client_buffer.clients():
        return JSONResponse(status_code=404, content={
            "error": "Cliente no conectado",
            "client_id": client_id
        })

    def generate():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        last_frame = None

        while True:
            try:
                if not client_buffer:
                    time.sleep(0.1)
                    continue

                frame_bytes = client_buffer.read(client_id)
                if frame_bytes:
                    if frame_bytes != last_frame:
                        last_frame = frame_bytes
                        yield boundary + frame_bytes + b"\r\n"
                    else:
                        time.sleep(0.03)
                else:
                    if client_id not in client_buffer.clients():
                        break
                    time.sleep(0.05)
            except GeneratorExit:
                break
            except Exception as e:
                logger.warning(f"[MJPEG {client_id}] Error: {e}")
                break

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )
