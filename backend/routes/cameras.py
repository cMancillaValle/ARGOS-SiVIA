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
  POST   /api/camaras/disconnect      → Detener Athena
  GET    /api/camaras/stream          → Multipart stream del frame procesado
  GET    /api/camaras/eventos/stream  → SSE de eventos IA (solo vista Cámaras)
  GET    /api/camaras/athena/status   → Estado del motor Athena

v1.7.5: integración con AthenaManager (buffer global + SSE)
"""

import sqlite3
import os
import time
import json
import queue
import logging
from flask import Blueprint, request, jsonify, Response, stream_with_context
from services.auth_service import (
    requiere_auth, registrar_auditoria, requiere_permiso, validate_token,
)

logger = logging.getLogger(__name__)

cameras_bp = Blueprint('cameras', __name__)
DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db')
)

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
    - Si 'ip' == 'webcam'          → modo cámara cliente (navegador remoto)
    - Si 'ip' empieza con 'rtsp://', 'http://' → URL de stream de red
    - Si 'ip' es un dígito         → índice de cámara local del servidor
    - Fallback                     → índice 0 (cámara local por defecto)
    """
    ip = (cam_row.get('ip') or '').strip()
    if ip.lower() == 'webcam':
        return 'webcam'   # modo remoto: frames vienen del navegador vía WS
    if ip.startswith(('rtsp://', 'http://', 'https://')):
        return ip
    if ip.isdigit():
        return int(ip)
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
    - Fuente 'webcam': modo cliente remoto (frames llegan por WebSocket)
    - Fuente RTSP/índice: worker OpenCV normal
    """
    conn = get_conn()
    row  = conn.execute('SELECT * FROM camaras WHERE id=?', (cam_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Cámara no encontrada.'}), 404

    cam_data = dict(row)
    source   = _resolve_source(cam_data)   # 'webcam' | 'rtsp://...' | int

    # Leer umbral de confianza desde configuración del sistema
    confidence = _get_confidence()

    athena = _get_athena()
    if not athena:
        return jsonify({'error': 'Motor Athena no disponible (verifique dependencias de IA).'}), 503

    try:
        athena.start(cam_id=cam_id, source=source, confidence=confidence)
        registrar_auditoria(
            request.usuario['id'], 'ATHENA_CONECTADA',
            f'Athena iniciada en cámara {cam_data["codigo"]} (fuente: {source})'
        )
        modo = 'webcam-cliente' if str(source) == 'webcam' else str(source)
        return jsonify({
            'status':     'conectado',
            'cam_id':     cam_id,
            'codigo':     cam_data['codigo'],
            'source':     modo,
            'webcam_mode': str(source) == 'webcam',
            'confidence': confidence,
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
