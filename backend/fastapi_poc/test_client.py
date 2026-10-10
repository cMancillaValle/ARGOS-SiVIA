"""
backend/fastapi_poc/test_client.py
──────────────────────────────────────────────────────────────────────────────
Script de prueba automatizado para verificar el endpoint WebSocket FastAPI:
    WS /api/camaras/client/push

Casos de prueba cubiertos:
  1. Handshake exitoso con token válido y recepción de {type: "ok", client_id: ..., cam_id: ...}.
  2. Rechazo con token inválido ({type: "error", message: "No autorizado"}) y cierre.
  3. Rechazo ante ausencia de cam_id ({type: "error", message: "cam_id requerido"}).
  4. Envío y respuesta de Ping/Pong ({type: "ping"} → {type: "pong"}).
  5. Envío de frame JPEG codificado en Base64 y verificación de escritura en client_buffer.
  6. Desconexión del cliente y verificación de limpieza en client_buffer y mapa de cámaras.

Uso:
  # 1. Con el servidor FastAPI corriendo en segundo plano:
  python backend/fastapi_poc/test_client.py --ws-url ws://127.0.0.1:8001/api/camaras/client/push

  # 2. Modo autónomo in-process (utilizando TestClient de FastAPI):
  python backend/fastapi_poc/test_client.py
──────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import time
import base64
import argparse
import sqlite3

# Asegurar path de backend
BACKEND_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.auth_service import create_session, revoke_token, get_conn
from core_ia.athena.client_frame_buffer import client_buffer
from fastapi_poc.app import app, _client_cameras, get_client_camera


# Frame JPEG dummy 1x1 pixel mínimo para pruebas de transmisión
DUMMY_JPEG_BYTES = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
    b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
    b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342'
    b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4'
    b'\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00'
    b'\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
    b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
)
DUMMY_B64_FRAME = "data:image/jpeg;base64," + base64.b64encode(DUMMY_JPEG_BYTES).decode('ascii')


def get_or_create_test_token() -> str:
    """Obtiene un token de un usuario activo existente o genera una sesión válida de prueba."""
    try:
        conn = get_conn()
        row = conn.execute("SELECT id FROM usuarios WHERE activo = 1 LIMIT 1").fetchone()
        conn.close()
        if row:
            user_id = row['id']
            return create_session(user_id)
    except Exception as e:
        print(f"[!] Error conectando a BD: {e}")
    # Fallback: generar token simulado
    return "test_mock_token_12345"


def run_inprocess_tests():
    """Ejecuta los tests usando Starlette / FastAPI TestClient."""
    from starlette.testclient import TestClient

    print("\n========================================================")
    print(" EJECUTANDO SUITE DE PRUEBAS EN MODO IN-PROCESS (FastAPI)")
    print("========================================================\n")

    client = TestClient(app)

    # 1. Healthcheck HTTP
    res = client.get("/health")
    assert res.status_code == 200, f"Healthcheck falló: {res.text}"
    print(" [OK] GET /health responde HTTP 200 OK")

    token = get_or_create_test_token()
    print(f" [i] Token de prueba generado: {token[:10]}...")

    # 2. Test: Rechazo por Token Inválido
    print("\n--- Test 1: Rechazo con Token Inválido ---")
    with client.websocket_connect("/api/camaras/client/push") as ws:
        ws.send_text(json.dumps({"token": "token_invalido_xyz", "cam_id": 1}))
        response = json.loads(ws.receive_text())
        print(f"  Respuesta recibida: {response}")
        assert response.get("type") == "error"
        assert response.get("message") == "No autorizado"
        print("  [OK] Rechazado con mensaje 'No autorizado' correctamente")

    # 3. Test: Rechazo por cam_id faltante
    print("\n--- Test 2: Rechazo sin cam_id ---")
    with client.websocket_connect("/api/camaras/client/push") as ws:
        ws.send_text(json.dumps({"token": token}))
        response = json.loads(ws.receive_text())
        print(f"  Respuesta recibida: {response}")
        assert response.get("type") == "error"
        assert response.get("message") == "cam_id requerido"
        print("  [OK] Rechazado con mensaje 'cam_id requerido' correctamente")

    # 4. Test: Handshake exitoso, Ping/Pong, Frame Base64 y Limpieza al desconectar
    print("\n--- Test 3: Handshake OK, Ping/Pong, Frames & Limpieza ---")
    cam_test_id = 999
    with client.websocket_connect("/api/camaras/client/push") as ws:
        # Enviar Handshake
        ws.send_text(json.dumps({"token": token, "cam_id": cam_test_id}))
        handshake_res = json.loads(ws.receive_text())
        print(f"  Respuesta Handshake: {handshake_res}")
        assert handshake_res.get("type") == "ok"
        assert handshake_res.get("cam_id") == cam_test_id
        assigned_client_id = handshake_res.get("client_id")
        assert assigned_client_id is not None
        print(f"  [OK] Handshake OK, client_id asignado: {assigned_client_id}")

        # Verificar mapa de cámaras
        assert get_client_camera(assigned_client_id) == cam_test_id
        print(f"  [OK] Mapa _client_cameras verificado: {assigned_client_id} -> Cámara {cam_test_id}")

        # Enviar Ping
        ws.send_text(json.dumps({"type": "ping"}))
        ping_res = json.loads(ws.receive_text())
        print(f"  Respuesta Ping: {ping_res}")
        assert ping_res.get("type") == "pong"
        print("  [OK] Ping/Pong exitoso")

        # Enviar Frame JPEG en Base64
        ws.send_text(json.dumps({
            "type": "frame",
            "data": DUMMY_B64_FRAME,
            "ts": int(time.time() * 1000)
        }))

        # Dar margen breve para sincronización de escritura
        time.sleep(0.05)

        # Verificar que el frame llegó a client_buffer
        buffered_bytes = client_buffer.read(assigned_client_id)
        assert buffered_bytes is not None, "El frame no fue encontrado en client_buffer"
        assert buffered_bytes == DUMMY_JPEG_BYTES, "Los bytes del buffer no coinciden con el JPEG enviado"
        print(f"  [OK] Frame Base64 recibido y decodificado en client_buffer ({len(buffered_bytes)} bytes)")

    # 5. Verificar limpieza post-desconexión
    time.sleep(0.05)
    post_clients = client_buffer.clients()
    assert assigned_client_id not in post_clients, "client_id aún permanece en client_buffer tras desconexión"
    assert get_client_camera(assigned_client_id) is None, "client_id aún permanece en _client_cameras tras desconexión"
    print("  [OK] Limpieza exitosa: cliente removido de client_buffer y mapa de cámaras al desconectar")

    # Revocar token de prueba
    try:
        revoke_token(token)
    except Exception:
        pass

    print("\n========================================================")
    print(" TODOS LOS TESTS PASARON EXITOSAMENTE (100% COMPATIBLE)")
    print("========================================================\n")


def run_live_network_tests(ws_url: str):
    """Ejecuta los tests conectándose a través de la red WebSocket usando websockets."""
    import asyncio
    import websockets

    async def _async_live_tests():
        print(f"\n========================================================")
        print(f" EJECUTANDO TESTS CONTRA SERVIDOR REMOTO: {ws_url}")
        print(f"========================================================\n")

        token = get_or_create_test_token()
        print(f" [i] Token de prueba generado: {token[:10]}...")

        # 1. Rechazo con token inválido
        print("\n--- Test 1: Rechazo con Token Inválido ---")
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"token": "token_invalido", "cam_id": 1}))
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"  Respuesta: {data}")
            assert data.get("type") == "error" and data.get("message") == "No autorizado"
            print("  [OK] Rechazado con 'No autorizado' correctamente")

        # 2. Handshake válido, Ping, Frame
        print("\n--- Test 2: Handshake OK, Ping/Pong, Frames & Cierre ---")
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"token": token, "cam_id": 1}))
            handshake = json.loads(await ws.recv())
            print(f"  Respuesta Handshake: {handshake}")
            assert handshake.get("type") == "ok"
            cid = handshake.get("client_id")
            print(f"  [OK] Handshake exitoso, client_id: {cid}")

            # Ping
            await ws.send(json.dumps({"type": "ping"}))
            pong = json.loads(await ws.recv())
            print(f"  Respuesta Ping: {pong}")
            assert pong.get("type") == "pong"
            print("  [OK] Ping/Pong exitoso")

            # Frame
            await ws.send(json.dumps({
                "type": "frame",
                "data": DUMMY_B64_FRAME,
                "ts": int(time.time() * 1000)
            }))
            print(f"  [OK] Frame enviado exitosamente")

        print("\n========================================================")
        print(" TESTS DE RED COMPLETADOS CON ÉXITO")
        print("========================================================\n")

    asyncio.run(_async_live_tests())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test client para FastAPI WebSocket PoC")
    parser.add_argument("--ws-url", help="URL WebSocket (ej. ws://127.0.0.1:8001/api/camaras/client/push)")
    args = parser.parse_args()

    if args.ws_url:
        run_live_network_tests(args.ws_url)
    else:
        run_inprocess_tests()
