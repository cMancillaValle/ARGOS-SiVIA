"""
routes/cameras.py
─────────────────────────────────────────────────────────────────────────────
CRUD de cámaras + streaming de video en tiempo real con Athena IA integrada.

Endpoints CRUD:
  GET    /api/camaras              → Lista todas las cámaras
  POST   /api/camaras              → Crear cámara
  GET    /api/camaras/<id>         → Detalle de una cámara
  PUT    /api/camaras/<id>         → Actualizar cámara
  DELETE /api/camaras/<id>         → Eliminar cámara
  GET    /api/camaras/stats        → Resumen de estado

Endpoints IA / Streaming:
  POST   /api/camaras/<id>/connect    → Iniciar Athena en esa cámara
                                         ?mode=acceso|evasion  ?tripwire=0.55
  POST   /api/camaras/disconnect      → Detener Athena
  GET    /api/camaras/stream          → Multipart stream del frame procesado
  GET    /api/camaras/eventos/stream  → SSE de eventos IA (solo vista Cámaras)
  GET    /api/camaras/athena/status   → Estado del motor Athena
  POST   /api/camaras/upload-video    → Subir video .mp4/.avi para análisis
  GET    /api/camaras/videos          → Listar videos subidos

v1.7.5+: integración con AthenaManager (buffer global + SSE + modo evasión)
"""

import sqlite3
import os
import time
import json
import queue
import logging
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, Response, stream_with_context
from services.auth_service import (
    requiere_auth, registrar_auditoria, requiere_permiso, validate_token,
)

logger = logging.getLogger(__name__)

cameras_bp = Blueprint('cameras', __name__)
DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db')
)

# ── Directorio de videos subidos para análisis ────────────────────────────────
UPLOADS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads', 'videos')
)
os.makedirs(UPLOADS_DIR, exist_ok=True)
_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.webm', '.ts', '.flv'}

# ── Importar AthenaManager (lazy para no bloquear si CV2 no está disponible) ─
def _get_athena():
    try:
        import sys
        athena_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', 'core_ia', 'athena')
        )
        if athena_dir not in sys.path:
            sys.path.insert(0, athena_dir)
        from athena_engine import athena
        return athena
    except Exception as e:
        logger.warning(f"AthenaManager no disponible: {e}")
        return None


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_source(cam_row: dict):
    """
    Convierte los datos de la cámara en una fuente OpenCV válida.
    - Si 'ip' == 'webcam'                  → modo cámara cliente (navegador remoto)
    - Si 'ip' empieza con 'rtsp://', etc.  → URL de stream de red
    - Si 'ip' es un dígito                 → índice de cámara local del servidor
    - Si 'ip' es ruta de archivo de video  → ruta local (mp4, avi, mkv...)
    - Fallback                             → índice 0 (cámara local por defecto)
    """
    ip = (cam_row.get('ip') or '').strip()
    if ip.lower() == 'webcam':
        return 'webcam'
    if ip.startswith(('rtsp://', 'http://', 'https://')):
        return ip
    if ip.isdigit():
        return int(ip)
    # Verificar si es una ruta de archivo de video (absoluta o relativa a uploads)
    _, ext = os.path.splitext(ip.lower())
    if ext in _VIDEO_EXTENSIONS:
        # Si la ruta no es absoluta, buscarla en UPLOADS_DIR
        if not os.path.isabs(ip):
            candidate = os.path.join(UPLOADS_DIR, ip)
            if os.path.isfile(candidate):
                return candidate
        if os.path.isfile(ip):
            return ip
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# CRUD ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

# ── GET /api/camaras ──────────────────────────────────────────────────────────
@cameras_bp.route('', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver')
def list_cameras():
    """
    Query params:
      ?estado=activa|offline|mantenimiento
      ?estacion=Portal Norte
    """
    estado   = request.args.get('estado')
    estacion = request.args.get('estacion')

    query  = 'SELECT * FROM camaras WHERE 1=1'
    params = []
    if estado:
        query  += ' AND estado = ?'
        params.append(estado)
    if estacion:
        query  += ' AND estacion LIKE ?'
        params.append(f'%{estacion}%')
    query += ' ORDER BY codigo'

    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        'total':   len(rows),
        'camaras': [dict(r) for r in rows]
    })


# ── GET /api/camaras/stats ────────────────────────────────────────────────────
@cameras_bp.route('/stats', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver')
def camera_stats():
    conn     = get_conn()
    totales  = conn.execute('SELECT COUNT(*) FROM camaras').fetchone()[0]
    activas  = conn.execute("SELECT COUNT(*) FROM camaras WHERE estado='activa'").fetchone()[0]
    offline  = conn.execute("SELECT COUNT(*) FROM camaras WHERE estado='offline'").fetchone()[0]
    mant     = conn.execute("SELECT COUNT(*) FROM camaras WHERE estado='mantenimiento'").fetchone()[0]
    conn.close()
    return jsonify({
        'total': totales, 'activas': activas,
        'offline': offline, 'mantenimiento': mant,
    })


# ── GET /api/camaras/<id> ─────────────────────────────────────────────────────
@cameras_bp.route('/<int:cam_id>', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver_detalle')
def get_camera(cam_id):
    conn = get_conn()
    row  = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Cámara no encontrada.'}), 404
    return jsonify(dict(row))


# ── POST /api/camaras ─────────────────────────────────────────────────────────
@cameras_bp.route('', methods=['POST'])
@requiere_auth
@requiere_permiso('camaras:crear')
def create_camera():
    data = request.get_json(silent=True) or {}
    campos_requeridos = ['codigo', 'estacion', 'ubicacion']
    for campo in campos_requeridos:
        if not data.get(campo):
            return jsonify({'error': f'El campo "{campo}" es obligatorio.'}), 400

    conn = get_conn()
    try:
        cursor = conn.execute(
            'INSERT INTO camaras (codigo, estacion, ubicacion, estado, ip) VALUES (?,?,?,?,?)',
            (data['codigo'], data['estacion'], data['ubicacion'],
             data.get('estado', 'activa'), data.get('ip', ''))
        )
        conn.commit()
        cam = conn.execute('SELECT * FROM camaras WHERE id=?', (cursor.lastrowid,)).fetchone()
        conn.close()
        registrar_auditoria(request.usuario['id'], 'CAMARA_CREADA', f'Cámara {data["codigo"]} creada')
        return jsonify(dict(cam)), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f'El código "{data["codigo"]}" ya existe.'}), 409


# ── PUT /api/camaras/<id> ─────────────────────────────────────────────────────
@cameras_bp.route('/<int:cam_id>', methods=['PUT'])
@requiere_auth
@requiere_permiso('camaras:editar')
def update_camera(cam_id):
    data = request.get_json(silent=True) or {}
    campos_editables = ['estacion', 'ubicacion', 'estado', 'ip', 'fps', 'resolucion']

    sets, params = [], []
    for campo in campos_editables:
        if campo in data:
            sets.append(f'{campo} = ?')
            params.append(data[campo])

    if not sets:
        return jsonify({'error': 'No hay campos para actualizar.'}), 400

    params.append(cam_id)
    conn = get_conn()
    conn.execute(f'UPDATE camaras SET {", ".join(sets)} WHERE id=?', params)
    conn.commit()
    cam = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not cam:
        return jsonify({'error': 'Cámara no encontrada.'}), 404
    registrar_auditoria(request.usuario['id'], 'CAMARA_ACTUALIZADA', f'Cámara ID {cam_id}')
    return jsonify(dict(cam))


# ── DELETE /api/camaras/<id> ──────────────────────────────────────────────────
@cameras_bp.route('/<int:cam_id>', methods=['DELETE'])
@requiere_auth
@requiere_permiso('camaras:eliminar')
def delete_camera(cam_id):
    conn = get_conn()
    cam  = conn.execute('SELECT codigo FROM camaras WHERE id = ?', (cam_id,)).fetchone()
    if not cam:
        conn.close()
        return jsonify({'error': 'Cámara no encontrada.'}), 404
    conn.execute('DELETE FROM camaras WHERE id = ?', (cam_id,))
    conn.commit()
    conn.close()
    registrar_auditoria(request.usuario['id'], 'CAMARA_ELIMINADA', f'Cámara {cam["codigo"]} eliminada')
    return jsonify({'status': 'ok', 'mensaje': f'Cámara {cam["codigo"]} eliminada.'})


# ══════════════════════════════════════════════════════════════════════════════
# ATHENA IA — STREAMING Y CONTROL
# ══════════════════════════════════════════════════════════════════════════════

# ── POST /api/camaras/<id>/connect ────────────────────────────────────────────
@cameras_bp.route('/<int:cam_id>/connect', methods=['POST'])
@requiere_auth
def connect_camera(cam_id):
    """
    Arranca Athena apuntando a la cámara <cam_id>.

    Body JSON opcional:
      { "mode": "acceso" | "evasion", "tripwire": 0.55 }

    - mode=acceso  : control de acceso biométrico (por defecto)
    - mode=evasion : detección de colados TransMilenio (tracking + tripwire)
    - tripwire     : fracción Y de la línea del torniquete (0.1–0.9)
    """
    conn = get_conn()
    row  = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Cámara no encontrada.'}), 404

    cam_data   = dict(row)
    source     = _resolve_source(cam_data)
    confidence = _get_confidence()

    body     = request.get_json(silent=True) or {}
    mode     = body.get('mode', 'acceso').strip().lower()
    if mode not in ('acceso', 'evasion'):
        mode = 'acceso'
    tripwire = float(body.get('tripwire', 0.55))
    tripwire = max(0.1, min(0.9, tripwire))

    athena = _get_athena()
    if not athena:
        return jsonify({'error': 'Motor Athena no disponible (verifique dependencias de IA).'}), 503

    try:
        athena.start(
            cam_id=cam_id, source=source, confidence=confidence,
            mode=mode, tripwire=tripwire,
        )
        registrar_auditoria(
            request.usuario['id'], 'ATHENA_CONECTADA',
            f'Athena [{mode}] iniciada en cámara {cam_data["codigo"]} (fuente: {source})'
        )
        return jsonify({
            'status':      'conectado',
            'cam_id':      cam_id,
            'codigo':      cam_data['codigo'],
            'source':      'webcam-cliente' if str(source) == 'webcam' else str(source),
            'webcam_mode': str(source) == 'webcam',
            'mode':        mode,
            'tripwire':    tripwire,
            'confidence':  confidence,
        })
    except Exception as e:
        logger.error(f"Error al iniciar Athena cam={cam_id}: {e}", exc_info=True)
        return jsonify({'error': f'No se pudo iniciar Athena: {str(e)}'}), 500


# ── POST /api/camaras/disconnect ──────────────────────────────────────────────
@cameras_bp.route('/disconnect', methods=['POST'])
@requiere_auth
def disconnect_camera():
    """Detiene el hilo activo de Athena."""
    athena = _get_athena()
    if athena:
        athena.stop()
        registrar_auditoria(request.usuario['id'], 'ATHENA_DESCONECTADA', 'Motor Athena detenido')
    return jsonify({'status': 'desconectado'})


# ── GET /api/camaras/stream ───────────────────────────────────────────────────
@cameras_bp.route('/stream', methods=['GET'])
def stream_video():
    """
    Multipart MJPEG stream del frame procesado por Athena.
    Acepta token via query param:  /api/camaras/stream?t=<token>
    (Los navegadores no pueden enviar headers en requests de imagen)
    """
    if not _validate_token_qp():
        return Response('Unauthorized', status=401)

    athena = _get_athena()
    if not athena:
        return Response('Athena no disponible', status=503)

    def generate():
        yield from athena.generate_stream()

    return Response(
        stream_with_context(generate()),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma':        'no-cache',
            'Expires':       '0',
        }
    )


# ── GET /api/camaras/eventos/stream ──────────────────────────────────────────
@cameras_bp.route('/eventos/stream', methods=['GET'])
def eventos_sse():
    """
    Server-Sent Events: emite eventos IA detectados por Athena.
    Solo consume esta vista Cámaras del dashboard.
    Acepta token via query param:  /api/camaras/eventos/stream?t=<token>
    (EventSource del navegador no soporta headers personalizados)
    """
    if not _validate_token_qp():
        def _gen_unauth():
            yield f"data: {json.dumps({'error': 'No autorizado'})}\n\n"
        return Response(stream_with_context(_gen_unauth()),
                        mimetype='text/event-stream', status=401)

    athena = _get_athena()

    def generate():
        yield "retry: 3000\n\n"
        if not athena:
            yield f"data: {json.dumps({'error': 'Athena no disponible'})}\n\n"
            return
        while True:
            try:
                evento  = athena.event_queue.get(timeout=15)
                payload = json.dumps(evento, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            except queue.Empty:
                yield f": heartbeat {int(time.time())}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── GET /api/camaras/athena/status ───────────────────────────────────────────
@cameras_bp.route('/athena/status', methods=['GET'])
@requiere_auth
def athena_status():
    """Estado actual del motor Athena."""
    athena = _get_athena()
    if not athena:
        return jsonify({'available': False, 'running': False})
    status = athena.status()
    status['available'] = True
    return jsonify(status)


# ── Helper: validar token via query param (?t=) ───────────────────────────────
def _validate_token_qp() -> bool:
    """
    Para endpoints que el navegador consume directamente sin poder
    enviar headers (img src=, EventSource), acepta el token como
    query param '?t=<token>'  ADEMÁS del header X-Token habitual.
    """
    token = request.args.get('t') or request.headers.get('X-Token')
    return bool(validate_token(token))


# ── Helper: leer umbral de confianza desde BD / config ───────────────────────
def _get_confidence() -> float:
    """
    Intenta leer el umbral de confianza guardado en la BD.
    Si no existe, devuelve 0.50 por defecto.
    """
    try:
        conn = get_conn()
        row  = conn.execute(
            "SELECT valor FROM configuracion WHERE clave='ia_confidence_threshold' LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return float(row['valor'])
    except Exception:
        pass
    return 0.50


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO UPLOAD — Análisis de grabaciones
# ══════════════════════════════════════════════════════════════════════════════

# ── POST /api/camaras/upload-video ────────────────────────────────────────────
@cameras_bp.route('/upload-video', methods=['POST'])
@requiere_auth
@requiere_permiso('camaras:ver')
def upload_video():
    """
    Sube un archivo de video (.mp4, .avi, .mkv, .mov) al servidor para su análisis.
    El video queda guardado en backend/uploads/videos/ y puede usarse como fuente
    de una cámara configurando el campo 'ip' con el nombre del archivo.

    Cuerpo: multipart/form-data con campo 'video'.
    Retorna el nombre de archivo guardado y la ruta para asignarlo a una cámara.
    """
    if 'video' not in request.files:
        return jsonify({'error': 'No se encontró el campo "video" en el formulario.'}), 400

    archivo = request.files['video']
    if not archivo.filename:
        return jsonify({'error': 'El archivo no tiene nombre.'}), 400

    _, ext = os.path.splitext(archivo.filename.lower())
    if ext not in _VIDEO_EXTENSIONS:
        return jsonify({
            'error': f'Extensión "{ext}" no permitida. Use: {", ".join(sorted(_VIDEO_EXTENSIONS))}'
        }), 415

    nombre_seguro = secure_filename(archivo.filename)
    # Añadir timestamp para evitar colisiones de nombres
    base, extension = os.path.splitext(nombre_seguro)
    nombre_final = f"{base}_{int(time.time())}{extension}"
    ruta_destino = os.path.join(UPLOADS_DIR, nombre_final)

    archivo.save(ruta_destino)
    tamano_mb = round(os.path.getsize(ruta_destino) / (1024 * 1024), 2)

    registrar_auditoria(
        request.usuario['id'], 'VIDEO_SUBIDO',
        f'Video "{nombre_final}" subido ({tamano_mb} MB)'
    )
    logger.info(f"Video guardado: {ruta_destino} ({tamano_mb} MB)")

    return jsonify({
        'status':       'ok',
        'nombre':       nombre_final,
        'ruta':         ruta_destino,
        'tamano_mb':    tamano_mb,
        'instruccion':  f'Asigna ip="{nombre_final}" a una cámara y conecta en modo evasion',
    }), 201


# ── GET /api/camaras/videos ───────────────────────────────────────────────────
@cameras_bp.route('/videos', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver')
def listar_videos():
    """Lista todos los videos disponibles en el directorio de uploads."""
    videos = []
    try:
        for nombre in sorted(os.listdir(UPLOADS_DIR)):
            _, ext = os.path.splitext(nombre.lower())
            if ext in _VIDEO_EXTENSIONS:
                ruta = os.path.join(UPLOADS_DIR, nombre)
                tamano_mb = round(os.path.getsize(ruta) / (1024 * 1024), 2)
                videos.append({
                    'nombre':    nombre,
                    'tamano_mb': tamano_mb,
                    'ruta':      ruta,
                })
    except Exception as e:
        logger.warning(f"Error listando videos: {e}")

    return jsonify({'total': len(videos), 'videos': videos})

