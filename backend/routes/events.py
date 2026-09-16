"""
routes/events.py
────────────────
GET  /api/eventos                  → Lista eventos (filtrable)
POST /api/eventos                  → Registrar evento (sistema IA)
GET  /api/eventos/<id>             → Detalle de evento
PUT  /api/eventos/<id>/estado      → Confirmar / descartar evento
GET  /api/eventos/pendientes       → Solo eventos pendientes

FIX v1.2.1: Reemplazado chequeo manual de rol en update_event_status
            por @requiere_permiso('eventos:revisar').
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify
from services.auth_service import (
    requiere_auth, registrar_auditoria,
    requiere_permiso,
)

events_bp = Blueprint('events', __name__)
DB_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── GET /api/eventos ──────────────────────────────────
@events_bp.route('', methods=['GET'])
@requiere_auth
@requiere_permiso('eventos:ver')
def list_events():
    """
    Query params:
      ?estado=pendiente|confirmado|descartado
      ?tipo=evasion|intrusion|caida|otro
      ?estacion=Portal Norte
      ?limite=50
      ?pagina=1
    """
    estado   = request.args.get('estado')
    tipo     = request.args.get('tipo')
    estacion = request.args.get('estacion')
    limite   = min(int(request.args.get('limite', 50)), 200)
    pagina   = max(int(request.args.get('pagina', 1)), 1)
    offset   = (pagina - 1) * limite

    query = '''
        SELECT e.id, e.tipo, e.confianza, e.estado, e.observaciones,
               e.detectado_en, e.revisado_en,
               c.codigo as camara_codigo, c.estacion, c.ubicacion,
               u.nombre as operador_nombre
        FROM eventos e
        JOIN camaras c ON c.id = e.camara_id
        LEFT JOIN usuarios u ON u.id = e.operador_id
        WHERE 1=1
    '''
    params = []
    if estado:
        query += ' AND e.estado = ?';   params.append(estado)
    if tipo:
        query += ' AND e.tipo = ?';     params.append(tipo)
    if estacion:
        query += ' AND c.estacion LIKE ?'; params.append(f'%{estacion}%')
    query += f' ORDER BY e.detectado_en DESC LIMIT ? OFFSET ?'
    params += [limite, offset]

    conn  = get_conn()
    total = conn.execute(
        'SELECT COUNT(*) FROM eventos e JOIN camaras c ON c.id=e.camara_id WHERE 1=1' +
        (' AND e.estado=?' if estado else '') +
        (' AND e.tipo=?' if tipo else '') +
        (' AND c.estacion LIKE ?' if estacion else ''),
        [p for p, cond in [(estado, estado), (tipo, tipo), (f'%{estacion}%', estacion)] if cond]
    ).fetchone()[0]
    rows  = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        'total':   total,
        'pagina':  pagina,
        'limite':  limite,
        'eventos': [dict(r) for r in rows],
    })


# ── GET /api/eventos/pendientes ───────────────────────
@events_bp.route('/pendientes', methods=['GET'])
@requiere_auth
@requiere_permiso('eventos:ver')
def pending_events():
    conn = get_conn()
    rows = conn.execute(
        '''SELECT e.id, e.tipo, e.confianza, e.detectado_en,
                  c.codigo as camara_codigo, c.estacion, c.ubicacion
           FROM eventos e
           JOIN camaras c ON c.id = e.camara_id
           WHERE e.estado = 'pendiente'
           ORDER BY e.detectado_en DESC
           LIMIT 50'''
    ).fetchall()
    conn.close()
    return jsonify({'total': len(rows), 'eventos': [dict(r) for r in rows]})


# ── GET /api/eventos/<id> ─────────────────────────────
@events_bp.route('/<int:event_id>', methods=['GET'])
@requiere_auth
@requiere_permiso('eventos:ver_detalle')
def get_event(event_id):
    conn = get_conn()
    row = conn.execute(
        '''SELECT e.*, c.codigo as camara_codigo, c.estacion, c.ubicacion,
                  u.nombre as operador_nombre
           FROM eventos e
           JOIN camaras c ON c.id = e.camara_id
           LEFT JOIN usuarios u ON u.id = e.operador_id
           WHERE e.id = ?''',
        (event_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Evento no encontrado.'}), 404
    return jsonify(dict(row))


# ── POST /api/eventos ─────────────────────────────────
@events_bp.route('', methods=['POST'])
@requiere_auth
@requiere_permiso('eventos:crear')
def create_event():
    """Usado por el sistema de IA para registrar detecciones."""
    data = request.get_json(silent=True) or {}
    if not data.get('camara_id') or data.get('confianza') is None:
        return jsonify({'error': '"camara_id" y "confianza" son obligatorios.'}), 400

    conn = get_conn()
    cursor = conn.execute(
        '''INSERT INTO eventos (camara_id, tipo, confianza, estado)
           VALUES (?, ?, ?, 'pendiente')''',
        (data['camara_id'], data.get('tipo', 'evasion'), data['confianza'])
    )
    conn.commit()
    ev = conn.execute('SELECT * FROM eventos WHERE id=?', (cursor.lastrowid,)).fetchone()
    conn.close()
    return jsonify(dict(ev)), 201


# ── PUT /api/eventos/<id>/estado ──────────────────────
@events_bp.route('/<int:event_id>/estado', methods=['PUT'])
@requiere_auth
@requiere_permiso('eventos:revisar')          # ← FIX: antes era chequeo manual de rol
def update_event_status(event_id):
    """
    Body: { "estado": "confirmado"|"descartado", "observaciones": "..." }
    """
    data   = request.get_json(silent=True) or {}
    estado = data.get('estado')
    if estado not in ('confirmado', 'descartado'):
        return jsonify({'error': 'Estado debe ser "confirmado" o "descartado".'}), 400

    from datetime import datetime
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn  = get_conn()
    ev    = conn.execute('SELECT id FROM eventos WHERE id=?', (event_id,)).fetchone()
    if not ev:
        conn.close()
        return jsonify({'error': 'Evento no encontrado.'}), 404

    conn.execute(
        'UPDATE eventos SET estado=?, observaciones=?, operador_id=?, revisado_en=? WHERE id=?',
        (estado, data.get('observaciones', ''), request.usuario['id'], ahora, event_id)
    )
    conn.commit()
    updated = conn.execute('SELECT * FROM eventos WHERE id=?', (event_id,)).fetchone()
    conn.close()
    registrar_auditoria(request.usuario['id'], 'EVENTO_REVISADO',
                        f'Evento {event_id} marcado como {estado}')
    return jsonify(dict(updated))
