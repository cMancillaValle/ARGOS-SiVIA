"""
routes/cameras.py
──────────────────────────────────────────────────────────────────────────────
CRUD de cámaras + streaming de video en tiempo real con Athena IA integrada.

Endpoints CRUD:
  GET    /api/camaras
  POST   /api/camaras
  GET    /api/camaras/<id>
  PUT    /api/camaras/<id>
  DELETE /api/camaras/<id>
  GET    /api/camaras/stats

Endpoints IA / Streaming:
  POST   /api/camaras/<id>/connect
  POST   /api/camaras/<id>/disconnect
  GET    /api/camaras/<id>/stream
  GET    /api/camaras/eventos/stream
  GET    /api/camaras/athena/status

Video:
  POST   /api/camaras/upload-video
  GET    /api/camaras/videos

Soporte multi-cámara:
  - Cada cámara tiene su propio worker Athena.
  - Cada cámara tiene su propio stream.
  - Las webcams de navegador utilizan client_id independiente.
  - Desconectar una cámara no afecta a las demás.
"""

import sqlite3
import os
import time
import json
import queue
import logging

from werkzeug.utils import secure_filename

from flask import (
    Blueprint,
    request,
    jsonify,
    Response,
    stream_with_context
)

from services.auth_service import (
    requiere_auth,
    registrar_auditoria,
    requiere_permiso,
    validate_token,
)


logger = logging.getLogger(__name__)

cameras_bp = Blueprint('cameras', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..',
        '..',
        'database',
        'argos.db'
    )
)


# ─────────────────────────────────────────────────────────────────────────────
# VIDEOS SUBIDOS
# ─────────────────────────────────────────────────────────────────────────────

UPLOADS_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..',
        'uploads',
        'videos'
    )
)

os.makedirs(UPLOADS_DIR, exist_ok=True)

_VIDEO_EXTENSIONS = {
    '.mp4',
    '.avi',
    '.mkv',
    '.mov',
    '.webm',
    '.ts',
    '.flv'
}


# ─────────────────────────────────────────────────────────────────────────────
# ATHENA
# ─────────────────────────────────────────────────────────────────────────────
def _get_athena():
    """
    Importación lazy de AthenaManager.

    Se mantiene lazy para evitar problemas si OpenCV/IA
    todavía no está disponible al iniciar Flask.
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

        from core_ia.athena.athena_engine import athena

        return athena

    except Exception as e:
        logger.warning(
            f"AthenaManager no disponible: {e}"
        )

        return None

# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

def get_conn():

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    return conn


# ─────────────────────────────────────────────────────────────────────────────
# RESOLVER FUENTE DE CÁMARA
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_source(cam_row: dict):
    """
    Convierte los datos de la cámara en una fuente OpenCV válida.

    Reglas:

      ip == webcam
          → cámara del navegador cliente

      rtsp:// / http:// / https://
          → stream de red

      número
          → índice de cámara local

      archivo de video
          → video almacenado localmente

      cualquier otro caso
          → cámara local 0
    """

    ip = (cam_row.get('ip') or '').strip()

    if ip.lower() == 'webcam':
        return 'webcam'

    if ip.startswith((
        'rtsp://',
        'http://',
        'https://'
    )):
        return ip

    if ip.isdigit():
        return int(ip)

    _, ext = os.path.splitext(
        ip.lower()
    )

    if ext in _VIDEO_EXTENSIONS:

        if not os.path.isabs(ip):

            candidate = os.path.join(
                UPLOADS_DIR,
                ip
            )

            if os.path.isfile(candidate):
                return candidate

        if os.path.isfile(ip):
            return ip

    return 0


# ══════════════════════════════════════════════════════════════════════════════
# CRUD ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route('', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver')
def list_cameras():

    estado = request.args.get('estado')
    estacion = request.args.get('estacion')

    query = 'SELECT * FROM camaras WHERE 1=1'
    params = []

    if estado:

        query += ' AND estado = ?'

        params.append(estado)

    if estacion:

        query += ' AND estacion LIKE ?'

        params.append(
            f'%{estacion}%'
        )

    query += ' ORDER BY codigo'

    conn = get_conn()

    rows = conn.execute(
        query,
        params
    ).fetchall()

    conn.close()

    return jsonify({
        'total': len(rows),
        'camaras': [
            dict(r)
            for r in rows
        ]
    })


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras/stats
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route('/stats', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver')
def camera_stats():

    conn = get_conn()

    totales = conn.execute(
        'SELECT COUNT(*) FROM camaras'
    ).fetchone()[0]

    activas = conn.execute(
        "SELECT COUNT(*) FROM camaras WHERE estado='activa'"
    ).fetchone()[0]

    offline = conn.execute(
        "SELECT COUNT(*) FROM camaras WHERE estado='offline'"
    ).fetchone()[0]

    mant = conn.execute(
        "SELECT COUNT(*) FROM camaras WHERE estado='mantenimiento'"
    ).fetchone()[0]

    conn.close()

    return jsonify({
        'total': totales,
        'activas': activas,
        'offline': offline,
        'mantenimiento': mant
    })


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras/<id>
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route('/<int:cam_id>', methods=['GET'])
@requiere_auth
@requiere_permiso('camaras:ver_detalle')
def get_camera(cam_id):

    conn = get_conn()

    row = conn.execute(
        'SELECT * FROM camaras WHERE id=?',
        (cam_id,)
    ).fetchone()

    conn.close()

    if not row:

        return jsonify({
            'error': 'Cámara no encontrada.'
        }), 404

    return jsonify(
        dict(row)
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/camaras
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route('', methods=['POST'])
@requiere_auth
@requiere_permiso('camaras:crear')
def create_camera():

    data = request.get_json(
        silent=True
    ) or {}

    campos_requeridos = [
        'codigo',
        'estacion',
        'ubicacion'
    ]

    for campo in campos_requeridos:

        if not data.get(campo):

            return jsonify({
                'error':
                    f'El campo "{campo}" es obligatorio.'
            }), 400

    conn = get_conn()

    try:

        cursor = conn.execute(
            '''
            INSERT INTO camaras
            (codigo, estacion, ubicacion, estado, ip)
            VALUES (?,?,?,?,?)
            ''',
            (
                data['codigo'],
                data['estacion'],
                data['ubicacion'],
                data.get(
                    'estado',
                    'activa'
                ),
                data.get(
                    'ip',
                    ''
                )
            )
        )

        conn.commit()

        cam = conn.execute(
            'SELECT * FROM camaras WHERE id=?',
            (cursor.lastrowid,)
        ).fetchone()

        conn.close()

        registrar_auditoria(
            request.usuario['id'],
            'CAMARA_CREADA',
            f'Cámara {data["codigo"]} creada'
        )

        return jsonify(
            dict(cam)
        ), 201

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify({
            'error':
                f'El código "{data["codigo"]}" ya existe.'
        }), 409


# ─────────────────────────────────────────────────────────────────────────────
# PUT /api/camaras/<id>
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route('/<int:cam_id>', methods=['PUT'])
@requiere_auth
@requiere_permiso('camaras:editar')
def update_camera(cam_id):

    data = request.get_json(
        silent=True
    ) or {}

    campos_editables = [
        'estacion',
        'ubicacion',
        'estado',
        'ip',
        'fps',
        'resolucion'
    ]

    sets = []
    params = []

    for campo in campos_editables:

        if campo in data:

            sets.append(
                f'{campo} = ?'
            )

            params.append(
                data[campo]
            )

    if not sets:

        return jsonify({
            'error':
                'No hay campos para actualizar.'
        }), 400

    params.append(cam_id)

    conn = get_conn()

    conn.execute(
        f'''
        UPDATE camaras
        SET {", ".join(sets)}
        WHERE id=?
        ''',
        params
    )

    conn.commit()

    cam = conn.execute(
        'SELECT * FROM camaras WHERE id=?',
        (cam_id,)
    ).fetchone()

    conn.close()

    if not cam:

        return jsonify({
            'error':
                'Cámara no encontrada.'
        }), 404

    registrar_auditoria(
        request.usuario['id'],
        'CAMARA_ACTUALIZADA',
        f'Cámara ID {cam_id}'
    )

    return jsonify(
        dict(cam)
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/camaras/<id>
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route('/<int:cam_id>', methods=['DELETE'])
@requiere_auth
@requiere_permiso('camaras:eliminar')
def delete_camera(cam_id):

    conn = get_conn()

    cam = conn.execute(
        'SELECT codigo FROM camaras WHERE id=?',
        (cam_id,)
    ).fetchone()

    if not cam:

        conn.close()

        return jsonify({
            'error':
                'Cámara no encontrada.'
        }), 404

    # Detener Athena de esta cámara antes de eliminarla.
    athena = _get_athena()

    if athena:

        try:
            athena.stop(cam_id)
        except Exception as e:

            logger.warning(
                f"No se pudo detener Athena "
                f"cam={cam_id}: {e}"
            )

    conn.execute(
        'DELETE FROM camaras WHERE id=?',
        (cam_id,)
    )

    conn.commit()

    conn.close()

    registrar_auditoria(
        request.usuario['id'],
        'CAMARA_ELIMINADA',
        f'Cámara {cam["codigo"]} eliminada'
    )

    return jsonify({
        'status': 'ok',
        'mensaje':
            f'Cámara {cam["codigo"]} eliminada.'
    })


# ══════════════════════════════════════════════════════════════════════════════
# ATHENA IA — MULTI-CÁMARA
# ══════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/camaras/<id>/connect
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/<int:cam_id>/connect',
    methods=['POST']
)
@requiere_auth
def connect_camera(cam_id):
    """
    Inicia Athena únicamente para la cámara indicada.

    Body JSON:

    {
        "mode": "acceso",
        "tripwire": 0.55,
        "client_id": "XXXXXXXX"
    }

    client_id es obligatorio únicamente cuando la cámara
    utiliza una webcam enviada desde un navegador.
    """

    # ─────────────────────────────────────────────────────────────────────
    # Buscar cámara
    # ─────────────────────────────────────────────────────────────────────

    conn = get_conn()

    row = conn.execute(
        'SELECT * FROM camaras WHERE id=?',
        (cam_id,)
    ).fetchone()

    conn.close()

    if not row:

        return jsonify({
            'error':
                'Cámara no encontrada.'
        }), 404

    cam_data = dict(row)

    # ─────────────────────────────────────────────────────────────────────
    # Fuente
    # ─────────────────────────────────────────────────────────────────────

    source = _resolve_source(
        cam_data
    )

    is_webcam = (
        str(source).lower()
        == 'webcam'
    )

    # ─────────────────────────────────────────────────────────────────────
    # Configuración IA
    # ─────────────────────────────────────────────────────────────────────

    confidence = _get_confidence()

    body = request.get_json(
        silent=True
    ) or {}

    mode = body.get(
        'mode',
        'acceso'
    )

    if not isinstance(mode, str):
        mode = 'acceso'

    mode = mode.strip().lower()

    if mode not in (
        'acceso',
        'evasion'
    ):
        mode = 'acceso'

    try:

        tripwire = float(
            body.get(
                'tripwire',
                0.55
            )
        )

    except (
        TypeError,
        ValueError
    ):

        tripwire = 0.55

    tripwire = max(
        0.1,
        min(
            0.9,
            tripwire
        )
    )

    # ─────────────────────────────────────────────────────────────────────
    # CLIENT ID
    # ─────────────────────────────────────────────────────────────────────

    client_id = body.get(
        'client_id'
    )

    if client_id:

        client_id = str(
            client_id
        ).strip()

    # Si es webcam y no se envió client_id en la petición,
    # buscar si ya hay un cliente transmitiendo WebSocket para esta cámara.
    if is_webcam and not client_id:
        try:
            from routes.camera_client import get_client_by_camera
            client_id = get_client_by_camera(cam_id)
        except Exception as e:
            logger.warning(
                f"[Connect] No se pudo buscar cliente WS para cámara {cam_id}: {e}"
            )

    # Una webcam necesita identificar
    # el navegador que envía sus frames.

    if is_webcam and not client_id:

        return jsonify({
            'error':
                'No hay ninguna cámara/navegador transmitiendo para esta cámara. '
                'Activa la cámara en el navegador o inicia la transmisión.'
        }), 400

    # ─────────────────────────────────────────────────────────────────────
    # ATHENA
    # ─────────────────────────────────────────────────────────────────────

    athena = _get_athena()

    if not athena:

        return jsonify({
            'error':
                'Motor Athena no disponible '
                '(verifique dependencias de IA).'
        }), 503

    try:

        athena.start(
            cam_id=cam_id,
            source=source,
            confidence=confidence,
            mode=mode,
            tripwire=tripwire,
            client_id=client_id
        )

        registrar_auditoria(
            request.usuario['id'],
            'ATHENA_CONECTADA',
            (
                f'Athena [{mode}] iniciada '
                f'en cámara {cam_data["codigo"]} '
                f'(fuente: {source})'
            )
        )

        return jsonify({

            'status':
                'conectado',

            'cam_id':
                cam_id,

            'codigo':
                cam_data['codigo'],

            'source':
                (
                    'webcam-cliente'
                    if is_webcam
                    else str(source)
                ),

            'webcam_mode':
                is_webcam,

            'client_id':
                client_id,

            'mode':
                mode,

            'tripwire':
                tripwire,

            'confidence':
                confidence
        })

    except Exception as e:

        logger.error(
            f'Error al iniciar Athena '
            f'cam={cam_id}: {e}',
            exc_info=True
        )

        return jsonify({
            'error':
                f'No se pudo iniciar Athena: {str(e)}'
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/camaras/<id>/disconnect
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/<int:cam_id>/disconnect',
    methods=['POST']
)
@requiere_auth
def disconnect_camera(cam_id):
    """
    Detiene Athena únicamente para la cámara indicada.
    """

    athena = _get_athena()

    if not athena:

        return jsonify({
            'status':
                'desconectado',

            'cam_id':
                cam_id
        })

    try:

        athena.stop(
            cam_id
        )

        registrar_auditoria(
            request.usuario['id'],
            'ATHENA_DESCONECTADA',
            f'Motor Athena detenido en cámara {cam_id}'
        )

        return jsonify({
            'status':
                'desconectado',

            'cam_id':
                cam_id
        })

    except Exception as e:

        logger.error(
            f'Error deteniendo Athena '
            f'cam={cam_id}: {e}',
            exc_info=True
        )

        return jsonify({
            'error':
                f'No se pudo detener Athena: {str(e)}'
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras/<id>/stream
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/<int:cam_id>/stream',
    methods=['GET']
)
def stream_video(cam_id):
    """
    Stream MJPEG procesado por Athena para una cámara específica.

    Uso:

        /api/camaras/1/stream?t=<token>
        /api/camaras/2/stream?t=<token>
    """

    if not _validate_token_qp():

        return Response(
            'Unauthorized',
            status=401
        )

    athena = _get_athena()

    if not athena:

        return Response(
            'Athena no disponible',
            status=503
        )

    try:

        if not athena.is_running(
            cam_id
        ):

            return Response(
                'Cámara no está ejecutando Athena',
                status=404
            )

    except Exception as e:

        logger.warning(
            f'Error comprobando estado '
            f'cam={cam_id}: {e}'
        )

        return Response(
            'Estado de cámara no disponible',
            status=503
        )

    def generate():

        yield from athena.generate_stream(
            cam_id
        )

    return Response(

        stream_with_context(
            generate()
        ),

        mimetype=(
            'multipart/x-mixed-replace; '
            'boundary=frame'
        ),

        headers={

            'Cache-Control':
                'no-cache, no-store, must-revalidate',

            'Pragma':
                'no-cache',

            'Expires':
                '0'
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras/eventos/stream
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/eventos/stream',
    methods=['GET']
)
def eventos_sse():
    """
    SSE global de eventos IA.

    Cada evento contiene cam_id, por lo que el frontend
    puede determinar a qué cámara pertenece.
    """

    if not _validate_token_qp():

        def _gen_unauth():

            yield (
                'data: '
                + json.dumps({
                    'error':
                        'No autorizado'
                })
                + '\n\n'
            )

        return Response(
            stream_with_context(
                _gen_unauth()
            ),
            mimetype='text/event-stream',
            status=401
        )

    athena = _get_athena()

    def generate():

        yield 'retry: 3000\n\n'

        if not athena:

            yield (
                'data: '
                + json.dumps({
                    'error':
                        'Athena no disponible'
                })
                + '\n\n'
            )

            return

        while True:

            try:

                evento = athena.event_queue.get(
                    timeout=15
                )

                payload = json.dumps(
                    evento,
                    ensure_ascii=False
                )

                yield (
                    f'data: {payload}\n\n'
                )

            except queue.Empty:

                yield (
                    f': heartbeat '
                    f'{int(time.time())}\n\n'
                )

    return Response(

        stream_with_context(
            generate()
        ),

        mimetype='text/event-stream',

        headers={
            'Cache-Control':
                'no-cache',

            'X-Accel-Buffering':
                'no'
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras/athena/status
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/athena/status',
    methods=['GET']
)
@requiere_auth
def athena_status():
    """
    Estado de todas las instancias Athena.
    """

    athena = _get_athena()

    if not athena:

        return jsonify({
            'available':
                False,

            'running':
                False,

            'cameras':
                {}
        })

    try:

        status = athena.status()

        status['available'] = True

        return jsonify(
            status
        )

    except Exception as e:

        logger.error(
            f'Error obteniendo estado Athena: {e}',
            exc_info=True
        )

        return jsonify({
            'available':
                True,

            'running':
                False,

            'cameras':
                {},

            'error':
                str(e)
        }), 500


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# VALIDAR TOKEN QUERY PARAM
# ─────────────────────────────────────────────────────────────────────────────

def _validate_token_qp() -> bool:
    """
    Para endpoints consumidos directamente por el navegador
    acepta:

        ?t=<token>

    o:

        X-Token: <token>
    """

    token = (
        request.args.get('t')
        or request.headers.get('X-Token')
    )

    return bool(
        validate_token(token)
    )


# ─────────────────────────────────────────────────────────────────────────────
# OBTENER CONFIANZA
# ─────────────────────────────────────────────────────────────────────────────

def _get_confidence() -> float:
    """
    Lee el umbral de confianza desde la BD.

    Si no existe:
        0.50
    """

    try:

        conn = get_conn()

        row = conn.execute(
            '''
            SELECT valor
            FROM configuracion
            WHERE clave='ia_confidence_threshold'
            LIMIT 1
            '''
        ).fetchone()

        conn.close()

        if row:

            return float(
                row['valor']
            )

    except Exception:

        pass

    return 0.50


# ══════════════════════════════════════════════════════════════════════════════
# VIDEO UPLOAD
# ══════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/camaras/upload-video
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/upload-video',
    methods=['POST']
)
@requiere_auth
@requiere_permiso('camaras:ver')
def upload_video():

    if 'video' not in request.files:

        return jsonify({
            'error':
                'No se encontró el campo "video" en el formulario.'
        }), 400

    archivo = request.files['video']

    if not archivo.filename:

        return jsonify({
            'error':
                'El archivo no tiene nombre.'
        }), 400

    _, ext = os.path.splitext(
        archivo.filename.lower()
    )

    if ext not in _VIDEO_EXTENSIONS:

        return jsonify({
            'error':
                (
                    f'Extensión "{ext}" no permitida. '
                    f'Use: {", ".join(sorted(_VIDEO_EXTENSIONS))}'
                )
        }), 415

    nombre_seguro = secure_filename(
        archivo.filename
    )

    base, extension = os.path.splitext(
        nombre_seguro
    )

    nombre_final = (
        f'{base}_'
        f'{int(time.time())}'
        f'{extension}'
    )

    ruta_destino = os.path.join(
        UPLOADS_DIR,
        nombre_final
    )

    archivo.save(
        ruta_destino
    )

    tamano_mb = round(
        os.path.getsize(
            ruta_destino
        ) / (1024 * 1024),
        2
    )

    registrar_auditoria(
        request.usuario['id'],
        'VIDEO_SUBIDO',
        (
            f'Video "{nombre_final}" '
            f'subido ({tamano_mb} MB)'
        )
    )

    logger.info(
        f'Video guardado: '
        f'{ruta_destino} '
        f'({tamano_mb} MB)'
    )

    return jsonify({

        'status':
            'ok',

        'nombre':
            nombre_final,

        'ruta':
            ruta_destino,

        'tamano_mb':
            tamano_mb,

        'instruccion':
            (
                f'Asigna ip="{nombre_final}" '
                f'a una cámara y conecta '
                f'en modo evasion'
            )
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/camaras/videos
# ─────────────────────────────────────────────────────────────────────────────

@cameras_bp.route(
    '/videos',
    methods=['GET']
)
@requiere_auth
@requiere_permiso('camaras:ver')
def listar_videos():

    videos = []

    try:

        for nombre in sorted(
            os.listdir(
                UPLOADS_DIR
            )
        ):

            _, ext = os.path.splitext(
                nombre.lower()
            )

            if ext in _VIDEO_EXTENSIONS:

                ruta = os.path.join(
                    UPLOADS_DIR,
                    nombre
                )

                tamano_mb = round(
                    os.path.getsize(
                        ruta
                    ) / (1024 * 1024),
                    2
                )

                videos.append({

                    'nombre':
                        nombre,

                    'tamano_mb':
                        tamano_mb,

                    'ruta':
                        ruta
                })

    except Exception as e:

        logger.warning(
            f'Error listando videos: {e}'
        )

    return jsonify({
        'total':
            len(videos),

        'videos':
            videos
    })