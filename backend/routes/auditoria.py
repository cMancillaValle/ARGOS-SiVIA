"""
routes/auditoria.py
───────────────────
GET  /api/auditoria              → Log completo con filtros (admin/auditor)
GET  /api/auditoria/stats        → Stats en tiempo real para el dashboard
GET  /api/auditoria/export       → Descarga CSV
GET  /api/auditoria/chart        → Actividad por hora (hoy)
"""

import sqlite3
import os
import csv
import io
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, Response
from services.auth_service import requiere_auth, requiere_permiso

auditoria_bp = Blueprint('auditoria', __name__)
DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── GET /api/auditoria ────────────────────────────────
@auditoria_bp.route('', methods=['GET'])
@requiere_auth
@requiere_permiso('auditoria:ver')
def list_auditoria():
    """
    Query params:
      ?q=texto          → busca en accion, detalle, username, ip_origen
      ?usuario=username → filtra por username exacto
      ?fecha=YYYY-MM-DD → filtra por día
      ?limite=100
      ?pagina=1
    """
    q       = request.args.get('q', '').strip()
    usuario = request.args.get('usuario', '').strip()
    fecha   = request.args.get('fecha', '').strip()
    limite  = min(int(request.args.get('limite', 100)), 500)
    pagina  = max(int(request.args.get('pagina', 1)), 1)
    offset  = (pagina - 1) * limite

    base = """
        SELECT a.id, a.accion, a.detalle, a.ip_origen, a.fecha,
               u.username, u.nombre, u.rol
        FROM auditoria a
        LEFT JOIN usuarios u ON u.id = a.usuario_id
        WHERE 1=1
    """
    params = []

    if q:
        base += """ AND (
            a.accion    LIKE ? OR
            a.detalle   LIKE ? OR
            u.username  LIKE ? OR
            a.ip_origen LIKE ?
        )"""
        like = f'%{q}%'
        params += [like, like, like, like]

    if usuario:
        base += ' AND u.username = ?'
        params.append(usuario)

    if fecha:
        base += ' AND a.fecha LIKE ?'
        params.append(f'{fecha}%')

    conn   = get_conn()
    total  = conn.execute(f'SELECT COUNT(*) FROM ({base})', params).fetchone()[0]
    rows   = conn.execute(
        base + f' ORDER BY a.fecha DESC LIMIT ? OFFSET ?',
        params + [limite, offset]
    ).fetchall()

    # Lista de usuarios únicos para el filtro del frontend
    usuarios_unicos = conn.execute(
        'SELECT DISTINCT u.username FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE u.username IS NOT NULL ORDER BY u.username'
    ).fetchall()

    conn.close()
    return jsonify({
        'total':    total,
        'pagina':   pagina,
        'limite':   limite,
        'registros': [dict(r) for r in rows],
        'usuarios':  [r['username'] for r in usuarios_unicos],
    })


# ── GET /api/auditoria/stats ──────────────────────────
@auditoria_bp.route('/stats', methods=['GET'])
@requiere_auth
@requiere_permiso('auditoria:ver')
def auditoria_stats():
    """Stats en tiempo real para los stat cards."""
    conn = get_conn()
    now  = datetime.now()
    hoy  = now.strftime('%Y-%m-%d')
    h24  = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    d7   = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    d30  = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

    total_hoy = conn.execute(
        "SELECT COUNT(*) FROM auditoria WHERE fecha LIKE ?", (f'{hoy}%',)
    ).fetchone()[0]

    # Intentos fallidos = LOGIN con ip externa o accion de acceso denegado
    fallidos_24h = conn.execute(
        "SELECT COUNT(*) FROM auditoria WHERE fecha >= ? AND accion IN ('LOGIN_FALLIDO','ACCESO_DENEGADO')",
        (h24,)
    ).fetchone()[0]

    cambios_config_7d = conn.execute(
        """SELECT COUNT(*) FROM auditoria
           WHERE fecha >= ?
           AND accion IN ('CONFIG_ACTUALIZADA','MODELO_ACTUALIZADO','UMBRAL_MODIFICADO',
                          'CAMARA_ACTUALIZADA','CAMARA_CREADA','CAMARA_ELIMINADA')""",
        (d7,)
    ).fetchone()[0]

    exportaciones_30d = conn.execute(
        "SELECT COUNT(*) FROM auditoria WHERE fecha >= ? AND accion LIKE 'EXPORT%'",
        (d30,)
    ).fetchone()[0]

    total_registros = conn.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0]

    conn.close()
    return jsonify({
        'total_hoy':        total_hoy,
        'fallidos_24h':     fallidos_24h,
        'cambios_config_7d': cambios_config_7d,
        'exportaciones_30d': exportaciones_30d,
        'total_registros':   total_registros,
    })


# ── GET /api/auditoria/chart ──────────────────────────
@auditoria_bp.route('/chart', methods=['GET'])
@requiere_auth
@requiere_permiso('auditoria:ver')
def auditoria_chart():
    """Actividad por hora del día actual (24 buckets)."""
    hoy  = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    rows = conn.execute(
        """SELECT CAST(strftime('%H', fecha) AS INTEGER) as hora, COUNT(*) as total
           FROM auditoria
           WHERE fecha LIKE ?
           GROUP BY hora""",
        (f'{hoy}%',)
    ).fetchall()
    conn.close()

    buckets = {r['hora']: r['total'] for r in rows}
    chart   = [{'hora': h, 'total': buckets.get(h, 0)} for h in range(24)]
    return jsonify({'fecha': hoy, 'chart': chart})


# ── GET /api/auditoria/export ─────────────────────────
@auditoria_bp.route('/export', methods=['GET'])
@requiere_auth
@requiere_permiso('auditoria:ver')
def export_auditoria():
    """Descarga el log como CSV con los mismos filtros que list_auditoria."""
    q       = request.args.get('q', '').strip()
    usuario = request.args.get('usuario', '').strip()
    fecha   = request.args.get('fecha', '').strip()

    base = """
        SELECT a.id, a.fecha, u.username, u.nombre, u.rol,
               a.accion, a.detalle, a.ip_origen
        FROM auditoria a
        LEFT JOIN usuarios u ON u.id = a.usuario_id
        WHERE 1=1
    """
    params = []
    if q:
        base += " AND (a.accion LIKE ? OR a.detalle LIKE ? OR u.username LIKE ? OR a.ip_origen LIKE ?)"
        like = f'%{q}%'
        params += [like, like, like, like]
    if usuario:
        base += ' AND u.username = ?'
        params.append(usuario)
    if fecha:
        base += ' AND a.fecha LIKE ?'
        params.append(f'{fecha}%')

    conn = get_conn()
    rows = conn.execute(base + ' ORDER BY a.fecha DESC LIMIT 5000', params).fetchall()
    conn.close()

    # Registrar la propia exportación
    from services.auth_service import registrar_auditoria
    registrar_auditoria(
        request.usuario['id'], 'EXPORT_AUDITORIA',
        f'{len(rows)} registros exportados'
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Fecha', 'Username', 'Nombre', 'Rol', 'Acción', 'Detalle', 'IP Origen'])
    for r in rows:
        writer.writerow([
            r['id'], r['fecha'], r['username'] or '-', r['nombre'] or '-',
            r['rol'] or '-', r['accion'], r['detalle'] or '', r['ip_origen'] or '-'
        ])

    fecha_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=auditoria_argos_{fecha_str}.csv'}
    )
