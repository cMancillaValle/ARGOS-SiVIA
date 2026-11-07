"""
api/routers/cameras.py
──────────────────────────────────────────────────────────────────────────────
CRUD de cámaras + streaming de video en tiempo real con Athena IA integrada.

Endpoints CRUD:
  GET    /api/camaras
  POST   /api/camaras
  GET    /api/camaras/stats
  GET    /api/camaras/<id>
  PUT    /api/camaras/<id>
  DELETE /api/camaras/<id>

Endpoints IA / Streaming:
  POST   /api/camaras/<id>/connect
  POST   /api/camaras/<id>/disconnect
  GET    /api/camaras/<id>/stream          (MJPEG)
  GET    /api/camaras/eventos/stream       (SSE)
  GET    /api/camaras/athena/status

Video:
  POST   /api/camaras/upload-video
  GET    /api/camaras/videos
"""

import sqlite3
import os
import time
import json
import queue
import logging
import subprocess
import platform
import re
from typing import Optional

from werkzeug.utils import secure_filename
from fastapi import APIRouter, Request, Depends, UploadFile, File, Header
from fastapi.responses import JSONResponse, StreamingResponse, Response

from services.auth_service import (
    get_current_user,
    require_permission,
    require_any_permission,
    registrar_auditoria,
    validate_token,
    issue_stream_ticket,
    validate_stream_ticket,
    issue_sse_ticket,
    validate_sse_ticket,
    tiene_permiso,
)
from api.routers.camera_client import get_client_by_camera

logger = logging.getLogger(__name__)
router = APIRouter()

DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db')
)

UPLOADS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'uploads', 'videos')
)
os.makedirs(UPLOADS_DIR, exist_ok=True)

_VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.webm', '.ts', '.flv'
}


def _get_athena():
    """Importación lazy de AthenaManager."""
    try:
        from core_ia.athena.athena_engine import athena
        return athena
    except Exception as e:
        logger.warning(f"AthenaManager no disponible: {e}")
        return None


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _resolve_source(cam_row: dict):
    ip = (cam_row.get('ip') or '').strip()
    if ip.lower() == 'webcam':
        return 'webcam'
    if ip.startswith(('rtsp://', 'http://', 'https://')):
        return ip
    if ip.isdigit():
        return int(ip)
    _, ext = os.path.splitext(ip.lower())
    if ext in _VIDEO_EXTENSIONS:
        if not os.path.isabs(ip):
            candidate = os.path.join(UPLOADS_DIR, ip)
            if os.path.isfile(candidate):
                return candidate
        if os.path.isfile(ip):
            return ip
    return 0


def _get_confidence() -> float:
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT valor FROM configuracion WHERE clave='ia_confidence_threshold' LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return float(row['valor'])
    except Exception:
        pass
    return 0.50


# ══════════════════════════════════════════════════════════════════════════════
# CRUD ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("")
def list_cameras(
    estado: Optional[str] = None,
    estacion: Optional[str] = None,
    usuario: dict = Depends(require_permission("camaras:ver")),
):
    query = 'SELECT * FROM camaras WHERE 1=1'
    params = []
    if estado:
        query += ' AND estado = ?'
        params.append(estado)
    if estacion:
        query += ' AND estacion LIKE ?'
        params.append(f'%{estacion}%')
    query += ' ORDER BY codigo'

    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return JSONResponse(content={
        'total': len(rows),
        'camaras': [dict(r) for r in rows]
    })


@router.get("/stats")
def camera_stats(usuario: dict = Depends(require_permission("camaras:ver"))):
    conn = get_conn()
    totales = conn.execute('SELECT COUNT(*) FROM camaras').fetchone()[0]
    activas = conn.execute("SELECT COUNT(*) FROM camaras WHERE estado='activa'").fetchone()[0]
    offline = conn.execute("SELECT COUNT(*) FROM camaras WHERE estado='offline'").fetchone()[0]
    mant    = conn.execute("SELECT COUNT(*) FROM camaras WHERE estado='mantenimiento'").fetchone()[0]
    conn.close()

    return JSONResponse(content={
        'total': totales,
        'activas': activas,
        'offline': offline,
        'mantenimiento': mant
    })


@router.get("/videos")
def listar_videos(usuario: dict = Depends(require_permission("camaras:ver"))):
    videos = []
    try:
        for nombre in sorted(os.listdir(UPLOADS_DIR)):
            _, ext = os.path.splitext(nombre.lower())
            if ext in _VIDEO_EXTENSIONS:
                ruta = os.path.join(UPLOADS_DIR, nombre)
                tamano_mb = round(os.path.getsize(ruta) / (1024 * 1024), 2)
                videos.append({
                    'nombre': nombre,
                    'tamano_mb': tamano_mb,
                    'ruta': ruta
                })
    except Exception as e:
        logger.warning(f'Error listando videos: {e}')

    return JSONResponse(content={
        'total': len(videos),
        'videos': videos
    })


@router.post("/upload-video")
async def upload_video(
    request: Request,
    video: UploadFile = File(...),
    usuario: dict = Depends(require_permission("camaras:ver")),
):
    if not video.filename:
        return JSONResponse(status_code=400, content={'error': 'El archivo no tiene nombre.'})

    _, ext = os.path.splitext(video.filename.lower())
    if ext not in _VIDEO_EXTENSIONS:
        return JSONResponse(
            status_code=415,
            content={'error': f'Extensión "{ext}" no permitida. Use: {", ".join(sorted(_VIDEO_EXTENSIONS))}'}
        )

    nombre_seguro = secure_filename(video.filename)
    base, extension = os.path.splitext(nombre_seguro)
    nombre_final = f'{base}_{int(time.time())}{extension}'
    ruta_destino = os.path.join(UPLOADS_DIR, nombre_final)

    contents = await video.read()
    with open(ruta_destino, "wb") as f:
        f.write(contents)

    tamano_mb = round(os.path.getsize(ruta_destino) / (1024 * 1024), 2)
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'VIDEO_SUBIDO', f'Video "{nombre_final}" subido ({tamano_mb} MB)', ip)

    return JSONResponse(
        status_code=201,
        content={
            'status': 'ok',
            'nombre': nombre_final,
            'ruta': ruta_destino,
            'tamano_mb': tamano_mb,
            'instruccion': f'Asigna ip="{nombre_final}" a una cámara y conecta en modo evasion'
        }
    )


@router.get("/athena/status")
def athena_status(usuario: dict = Depends(get_current_user)):
    athena = _get_athena()
    if not athena:
        return JSONResponse(content={
            'available': False,
            'running': False,
            'cameras': {}
        })

    try:
        status = athena.status()
        status['available'] = True
        return JSONResponse(content=status)
    except Exception as e:
        logger.error(f'Error obteniendo estado Athena: {e}', exc_info=True)
        return JSONResponse(status_code=500, content={
            'available': True,
            'running': False,
            'cameras': {},
            'error': str(e)
        })


@router.get("/athena/diagnostics")
def athena_diagnostics(
    cam_id: Optional[int] = None,
    usuario: dict = Depends(require_any_permission("camaras:ver", "camaras:ver_detalle")),
):
    """
    Telemetría en memoria por sesión Athena, sin exponer fuentes ni credenciales de cámara.
    Controlado por RBAC: requiere permiso para consultar cámaras.
    """
    if cam_id is not None:
        conn = get_conn()
        row = conn.execute('SELECT id FROM camaras WHERE id=?', (cam_id,)).fetchone()
        conn.close()
        if not row:
            return JSONResponse(status_code=404, content={'error': 'Cámara no encontrada.'})

    athena = _get_athena()
    if not athena:
        return JSONResponse(status_code=503, content={'error': 'Motor Athena no disponible'})
    try:
        return JSONResponse(content=athena.diagnostics_status(cam_id))
    except Exception as e:
        logger.error(f'Error obteniendo diagnóstico Athena: {e}', exc_info=True)
        return JSONResponse(status_code=500, content={'error': 'Diagnóstico no disponible'})


@router.post("/eventos/stream-ticket")
def solicitar_sse_ticket(
    usuario: dict = Depends(require_permission("eventos:ver")),
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
):
    if not x_token:
        return JSONResponse(status_code=401, content={'error': 'Token de sesión requerido.'})
    ticket = issue_sse_ticket(usuario['id'], x_token, ttl_seconds=90)
    return JSONResponse(content={
        'ticket': ticket,
        'expires_in': 90,
        'stream_url': f'/api/camaras/eventos/stream?sse_ticket={ticket}',
    })


@router.get("/eventos/stream")
def eventos_sse(request: Request):
    """
    SSE global de eventos IA.
    Acepta un ticket SSE efímero o la cabecera X-Token.
    """
    sse_ticket = request.query_params.get('sse_ticket')
    user = validate_sse_ticket(sse_ticket) if sse_ticket else validate_token(request.headers.get('X-Token'))
    if not user or not tiene_permiso(user, 'eventos:ver'):
        def _gen_unauth():
            yield 'data: ' + json.dumps({'error': 'No autorizado'}) + '\n\n'
        return StreamingResponse(
            _gen_unauth(),
            media_type='text/event-stream',
            status_code=401
        )

    athena = _get_athena()

    def generate():
        yield 'retry: 3000\n\n'
        if not athena:
            yield 'data: ' + json.dumps({'error': 'Athena no disponible'}) + '\n\n'
            return

        while True:
            try:
                evento = athena.event_queue.get(timeout=15)
                payload = json.dumps(evento, ensure_ascii=False)
                yield f'data: {payload}\n\n'
            except queue.Empty:
                yield f': heartbeat {int(time.time())}\n\n'

    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@router.get("/{cam_id}")
def get_camera(cam_id: int, usuario: dict = Depends(require_permission("camaras:ver_detalle"))):
    conn = get_conn()
    row = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse(status_code=404, content={'error': 'Cámara no encontrada.'})
    return JSONResponse(content=dict(row))


@router.post("")
async def create_camera(
    request: Request,
    usuario: dict = Depends(require_permission("camaras:crear")),
):
    data = await request.json()
    campos_requeridos = ['codigo', 'estacion', 'ubicacion']
    for campo in campos_requeridos:
        if not data.get(campo):
            return JSONResponse(status_code=400, content={'error': f'El campo "{campo}" es obligatorio.'})

    conn = get_conn()
    try:
        cursor = conn.execute(
            '''INSERT INTO camaras (codigo, estacion, ubicacion, estado, ip)
               VALUES (?,?,?,?,?)''',
            (data['codigo'], data['estacion'], data['ubicacion'],
             data.get('estado', 'activa'), data.get('ip', ''))
        )
        conn.commit()
        cam = conn.execute('SELECT * FROM camaras WHERE id=?', (cursor.lastrowid,)).fetchone()
        conn.close()

        ip = request.client.host if request.client else None
        registrar_auditoria(usuario['id'], 'CAMARA_CREADA', f'Cámara {data["codigo"]} creada', ip)
        return JSONResponse(status_code=201, content=dict(cam))
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse(status_code=409, content={'error': f'El código "{data["codigo"]}" ya existe.'})


@router.put("/{cam_id}")
async def update_camera(
    cam_id: int,
    request: Request,
    usuario: dict = Depends(require_permission("camaras:editar")),
):
    data = await request.json()
    campos_editables = ['estacion', 'ubicacion', 'estado', 'ip', 'fps', 'resolucion']
    sets = []
    params = []
    for campo in campos_editables:
        if campo in data:
            sets.append(f'{campo} = ?')
            params.append(data[campo])

    if not sets:
        return JSONResponse(status_code=400, content={'error': 'No hay campos para actualizar.'})

    params.append(cam_id)
    conn = get_conn()
    conn.execute(f'UPDATE camaras SET {", ".join(sets)} WHERE id=?', params)
    conn.commit()
    cam = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not cam:
        return JSONResponse(status_code=404, content={'error': 'Cámara no encontrada.'})

    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'CAMARA_ACTUALIZADA', f'Cámara ID {cam_id}', ip)
    return JSONResponse(content=dict(cam))


@router.delete("/{cam_id}")
async def delete_camera(
    cam_id: int,
    request: Request,
    usuario: dict = Depends(require_permission("camaras:eliminar")),
):
    conn = get_conn()
    cam = conn.execute('SELECT codigo FROM camaras WHERE id=?', (cam_id,)).fetchone()
    if not cam:
        conn.close()
        return JSONResponse(status_code=404, content={'error': 'Cámara no encontrada.'})

    athena = _get_athena()
    if athena:
        try:
            athena.stop(cam_id)
        except Exception as e:
            logger.warning(f"No se pudo detener Athena cam={cam_id}: {e}")

    try:
        conn.execute('DELETE FROM camaras WHERE id=?', (cam_id,))
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        return JSONResponse(
            status_code=409,
            content={'error': f'No se puede eliminar la cámara {cam["codigo"]} porque tiene eventos asociados registrados en el sistema.'}
        )
    conn.close()

    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'CAMARA_ELIMINADA', f'Cámara {cam["codigo"]} eliminada', ip)
    return JSONResponse(content={'status': 'ok', 'mensaje': f'Cámara {cam["codigo"]} eliminada.'})


@router.post("/{cam_id}/connect")
async def connect_camera(
    cam_id: int,
    request: Request,
    usuario: dict = Depends(get_current_user),
):
    request_started_at = time.perf_counter()
    conn = get_conn()
    row = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse(status_code=404, content={'error': 'Cámara no encontrada.'})

    cam_data = dict(row)
    source = _resolve_source(cam_data)
    is_webcam = str(source).lower() == 'webcam'
    confidence = _get_confidence()

    body = await request.json() if await _has_body(request) else {}
    mode = body.get('mode', 'acceso')
    if not isinstance(mode, str) or mode.strip().lower() not in ('acceso', 'evasion'):
        mode = 'acceso'
    else:
        mode = mode.strip().lower()

    try:
        tripwire = float(body.get('tripwire', 0.55))
    except (TypeError, ValueError):
        tripwire = 0.55
    tripwire = max(0.1, min(0.9, tripwire))

    client_id = body.get('client_id')
    if client_id:
        client_id = str(client_id).strip()

    if is_webcam and not client_id:
        try:
            client_id = get_client_by_camera(cam_id)
        except Exception as e:
            logger.warning(f"[Connect] No se pudo buscar cliente WS para cámara {cam_id}: {e}")

    if is_webcam and not client_id:
        return JSONResponse(
            status_code=400,
            content={
                'error': 'No hay ninguna cámara/navegador transmitiendo para esta cámara. '
                         'Activa la cámara en el navegador o inicia la transmisión.'
            }
        )

    athena = _get_athena()
    if not athena:
        return JSONResponse(
            status_code=503,
            content={'error': 'Motor Athena no disponible (verifique dependencias de IA).'}
        )

    try:
        athena.start(
            cam_id=cam_id,
            source=source,
            confidence=confidence,
            mode=mode,
            tripwire=tripwire,
            client_id=client_id,
            request_started_at=request_started_at,
        )

        ip = request.client.host if request.client else None
        registrar_auditoria(
            usuario['id'], 'ATHENA_CONECTADA',
            f'Athena [{mode}] iniciada en cámara {cam_data["codigo"]} (fuente: {source})',
            ip
        )

        return JSONResponse(content={
            'status': 'conectado',
            'cam_id': cam_id,
            'codigo': cam_data['codigo'],
            'source': 'webcam-cliente' if is_webcam else str(source),
            'webcam_mode': is_webcam,
            'client_id': client_id,
            'mode': mode,
            'tripwire': tripwire,
            'confidence': confidence
        })
    except Exception as e:
        logger.error(f'Error al iniciar Athena cam={cam_id}: {e}', exc_info=True)
        return JSONResponse(status_code=500, content={'error': f'No se pudo iniciar Athena: {str(e)}'})


@router.post("/{cam_id}/disconnect")
def disconnect_camera(
    cam_id: int,
    request: Request,
    usuario: dict = Depends(get_current_user),
):
    athena = _get_athena()
    if not athena:
        return JSONResponse(content={'status': 'desconectado', 'cam_id': cam_id})

    try:
        athena.stop(cam_id)
        ip = request.client.host if request.client else None
        registrar_auditoria(usuario['id'], 'ATHENA_DESCONECTADA', f'Motor Athena detenido en cámara {cam_id}', ip)
        return JSONResponse(content={'status': 'desconectado', 'cam_id': cam_id})
    except Exception as e:
        logger.error(f'Error deteniendo Athena cam={cam_id}: {e}', exc_info=True)
        return JSONResponse(status_code=500, content={'error': f'No se pudo detener Athena: {str(e)}'})


@router.post("/{cam_id}/stream-ticket")
def solicitar_stream_ticket(
    cam_id: int,
    usuario: dict = Depends(require_permission("camaras:ver")),
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
):
    """
    Emite un ticket efímero de corta duración (60s) para reproducir el stream MJPEG.
    Requiere autenticación válida y permiso 'camaras:ver'.
    """
    if not x_token:
        return JSONResponse(status_code=401, content={'error': 'Token de sesión requerido.'})
    ticket = issue_stream_ticket(
        usuario["id"], cam_id, ttl_seconds=60, session_token=x_token
    )
    return JSONResponse(content={
        "ticket": ticket,
        "cam_id": cam_id,
        "expires_in": 60,
        "stream_url": f"/api/camaras/{cam_id}/stream?stream_ticket={ticket}"
    })


@router.get("/{cam_id}/stream")
def stream_video(cam_id: int, request: Request):
    """
    Stream MJPEG procesado por Athena para una cámara específica.
    Seguridad:
    1. Autorización mediante stream_ticket efímero (?stream_ticket=<ticket>).
    2. Autorización directa mediante cabecera X-Token.
    Los tickets efímeros previenen la exposición de tokens de sesión ordinarios en URLs.
    """
    stream_ticket = request.query_params.get("stream_ticket")
    user = None
    if stream_ticket:
        user = validate_stream_ticket(stream_ticket, cam_id)
        if not user:
            return Response("Ticket de streaming inválido o expirado", status_code=401)
        if not tiene_permiso(user, "camaras:ver"):
            return Response("Acceso denegado: permiso camaras:ver requerido", status_code=403)
    else:
        # Validación de cabecera X-Token
        token = request.headers.get("X-Token")
        if not token:
            return Response("Unauthorized", status_code=401)
        user = validate_token(token)
        if not user:
            return Response("Unauthorized", status_code=401)
        if not tiene_permiso(user, "camaras:ver"):
            return Response("Acceso denegado: permiso camaras:ver requerido", status_code=403)

    athena = _get_athena()
    if not athena:
        return Response('Athena no disponible', status_code=503)

    try:
        if not athena.is_running(cam_id):
            return Response('Cámara no está ejecutando Athena', status_code=404)
    except Exception as e:
        logger.warning(f'Error comprobando estado cam={cam_id}: {e}')
        return Response('Estado de cámara no disponible', status_code=503)

    def generate():
        yield from athena.generate_stream(cam_id)

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)



# ── GET /api/camaras/{cam_id}/ping (F28: Diagnóstico Real) ──────────────────
@router.get("/{cam_id}/ping")
def ping_camera(
    cam_id: int,
    request: Request,
    usuario: dict = Depends(require_permission("camaras:ver")),
):
    """
    Ejecuta un diagnóstico real de conectividad de red contra la cámara especificada.
    Valida existencia en BD, sanitiza el host contra SSRF y ejecuta una prueba ICMP real con timeout estricto.
    """
    conn = get_conn()
    cam = conn.execute("SELECT id, codigo, ip, estado FROM camaras WHERE id = ?", (cam_id,)).fetchone()
    conn.close()

    if not cam:
        return JSONResponse(status_code=404, content={"error": f"Cámara con id {cam_id} no encontrada."})

    ip_raw = (cam['ip'] or '').strip()
    codigo = cam['codigo']

    if not ip_raw:
        return JSONResponse(content={
            "cam_id": cam_id,
            "codigo": codigo,
            "ip": None,
            "tipo": "no_configurada",
            "online": False,
            "latencia_ms": None,
            "detalle": "Dirección IP no configurada en el sistema."
        })

    if ip_raw.lower() == 'webcam':
        return JSONResponse(content={
            "cam_id": cam_id,
            "codigo": codigo,
            "ip": "webcam",
            "tipo": "webcam",
            "online": True,
            "latencia_ms": 0,
            "detalle": "Dispositivo local cliente (Webcam)."
        })

    if ip_raw.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')) or ip_raw == '0':
        return JSONResponse(content={
            "cam_id": cam_id,
            "codigo": codigo,
            "ip": ip_raw,
            "tipo": "archivo_o_dispositivo",
            "online": True,
            "latencia_ms": 0,
            "detalle": "Fuente sintética o archivo de video local."
        })

    # Extraer y sanitizar host
    host = ip_raw
    if '://' in host:
        host = host.split('://', 1)[1]
    if '/' in host:
        host = host.split('/', 1)[0]
    if '@' in host:
        host = host.split('@', 1)[1]
    if ':' in host:
        host = host.split(':', 1)[0]

    # Validación estricta de formato host / IP para prevenir inyección y SSRF
    if not re.match(r'^[a-zA-Z0-9.-]+$', host) or host.startswith('-'):
        return JSONResponse(status_code=400, content={
            "cam_id": cam_id,
            "codigo": codigo,
            "ip": ip_raw,
            "tipo": "invalida",
            "online": False,
            "latencia_ms": None,
            "detalle": "Formato de host o IP inválido para diagnóstico."
        })

    # Ejecución real de ping con timeout estricto
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    timeout_param = '-w' if platform.system().lower() == 'windows' else '-W'
    timeout_val = '1000' if platform.system().lower() == 'windows' else '1'
    cmd = ['ping', param, '1', timeout_param, timeout_val, host]

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0
        )
        elapsed_ms = round((time.time() - t0) * 1000, 1)
        out = proc.stdout

        if proc.returncode == 0:
            m = re.search(r'tiempo[=<](\d+)\s*ms|time[=<](\d+)\s*ms', out, re.I)
            lat = int(m.group(1) or m.group(2)) if m else elapsed_ms
            return JSONResponse(content={
                "cam_id": cam_id,
                "codigo": codigo,
                "ip": ip_raw,
                "tipo": "red_ip",
                "online": True,
                "latencia_ms": lat,
                "detalle": f"Conectado ({lat} ms)"
            })
        else:
            if 'inaccesible' in out.lower() or 'unreachable' in out.lower():
                detalle = "Host de cámara inaccesible en red"
            else:
                detalle = "Tiempo de espera agotado (Offline)"
            return JSONResponse(content={
                "cam_id": cam_id,
                "codigo": codigo,
                "ip": ip_raw,
                "tipo": "red_ip",
                "online": False,
                "latencia_ms": None,
                "detalle": detalle
            })
    except subprocess.TimeoutExpired:
        return JSONResponse(content={
            "cam_id": cam_id,
            "codigo": codigo,
            "ip": ip_raw,
            "tipo": "red_ip",
            "online": False,
            "latencia_ms": None,
            "detalle": "Tiempo límite agotado (Timeout >2s)"
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "cam_id": cam_id,
            "codigo": codigo,
            "ip": ip_raw,
            "tipo": "error",
            "online": False,
            "latencia_ms": None,
            "detalle": f"Fallo al ejecutar diagnóstico: {str(e)}"
        })
