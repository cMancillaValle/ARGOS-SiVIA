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
from typing import Optional

from werkzeug.utils import secure_filename
from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, Response

from services.auth_service import (
    get_current_user,
    require_permission,
    registrar_auditoria,
    validate_token,
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


def _validate_token_qp(request: Request) -> bool:
    token = request.query_params.get('t') or request.headers.get('X-Token')
    return bool(validate_token(token))


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


@router.get("/eventos/stream")
def eventos_sse(request: Request):
    """
    SSE global de eventos IA.
    Acepta ?t=<token> o cabecera X-Token.
    """
    if not _validate_token_qp(request):
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

    conn.execute('DELETE FROM camaras WHERE id=?', (cam_id,))
    conn.commit()
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
            client_id=client_id
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


@router.get("/{cam_id}/stream")
def stream_video(cam_id: int, request: Request):
    """
    Stream MJPEG procesado por Athena para una cámara específica.
    Acepta ?t=<token> o cabecera X-Token.
    """
    if not _validate_token_qp(request):
        return Response('Unauthorized', status_code=401)

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
