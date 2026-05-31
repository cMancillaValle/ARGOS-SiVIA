"""
routes/stats.py
───────────────
GET /api/stats         → Resumen general del sistema
GET /api/stats/hoy     → Actividad de las últimas 24h
GET /api/stats/auditoria → Log de acciones (solo admin/auditor)
"""

import sqlite3
import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from services.auth_service import requiere_auth, requiere_permiso

stats_bp = Blueprint('stats', __name__)
DB_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── GET /api/stats ────────────────────────────────────
@stats_bp.route('', methods=['GET'])
@requiere_auth
def general_stats():
    """Estadísticas generales del sistema ARGOS."""
    conn = get_conn()

    # Cámaras
    cam_total  = conn.execute('SELECT COUNT(*) FROM camaras').fetchone()[0]
    cam_activa = conn.execute('SELECT COUNT(*) FROM camaras WHERE estado="activa"').fetchone()[0]
    cam_offline= conn.execute('SELECT COUNT(*) FROM camaras WHERE estado="offline"').fetchone()[0]
    cam_mant   = conn.execute('SELECT COUNT(*) FROM camaras WHERE estado="mantenimiento"').fetchone()[0]

    # Eventos totales
    ev_total   = conn.execute('SELECT COUNT(*) FROM eventos').fetchone()[0]
    ev_pend    = conn.execute('SELECT COUNT(*) FROM eventos WHERE estado="pendiente"').fetchone()[0]
    ev_confirm = conn.execute('SELECT COUNT(*) FROM eventos WHERE estado="confirmado"').fetchone()[0]
    ev_desc    = conn.execute('SELECT COUNT(*) FROM eventos WHERE estado="descartado"').fetchone()[0]

    # Hoy
    hoy = datetime.now().strftime('%Y-%m-%d')
    ev_hoy  = conn.execute(
        'SELECT COUNT(*) FROM eventos WHERE detectado_en LIKE ?', (f'{hoy}%',)
    ).fetchone()[0]

    # Últimas 48 horas por hora (actividad)
    hace_48h = (datetime.now() - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
    por_hora = conn.execute(
        '''SELECT strftime('%Y-%m-%d %H:00', detectado_en) as hora, COUNT(*) as total
           FROM eventos
           WHERE detectado_en >= ?
           GROUP BY hora ORDER BY hora''',
        (hace_48h,)
    ).fetchall()

    # Usuarios activos
    usuarios = conn.execute('SELECT COUNT(*) FROM usuarios WHERE activo=1').fetchone()[0]

    # Tasa de precisión simulada (confirmados / (confirmados + descartados))
    precision = 0.0
    if ev_confirm + ev_desc > 0:
        precision = round(ev_confirm / (ev_confirm + ev_desc), 4)

    conn.close()
    return jsonify({
        'camaras': {
            'total': cam_total,
            'activas': cam_activa,
            'offline': cam_offline,
            'mantenimiento': cam_mant,
        },
        'eventos': {
            'total': ev_total,
            'pendientes': ev_pend,
            'confirmados': ev_confirm,
            'descartados': ev_desc,
            'hoy': ev_hoy,
        },
        'sistema': {
            'usuarios_activos': usuarios,
            'precision_modelo': precision,
            'fps_promedio': 15.4,
            'uptime_horas': 720,   # 30 días demo
        },
        'actividad_48h': [dict(r) for r in por_hora],
    })


# ── GET /api/stats/hoy ────────────────────────────────
@stats_bp.route('/hoy', methods=['GET'])
@requiere_auth
def stats_today():
    hoy  = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()

    eventos = conn.execute(
        '''SELECT e.id, e.tipo, e.confianza, e.estado, e.detectado_en,
                  c.codigo as camara_codigo, c.estacion
           FROM eventos e
           JOIN camaras c ON c.id = e.camara_id
           WHERE e.detectado_en LIKE ?
           ORDER BY e.detectado_en DESC''',
        (f'{hoy}%',)
    ).fetchall()

    # Agrupar por hora
    por_hora = conn.execute(
        '''SELECT strftime('%H', detectado_en) as hora, COUNT(*) as total
           FROM eventos WHERE detectado_en LIKE ?
           GROUP BY hora ORDER BY hora''',
        (f'{hoy}%',)
    ).fetchall()

    # Top estaciones
    top_estaciones = conn.execute(
        '''SELECT c.estacion, COUNT(*) as eventos
           FROM eventos e JOIN camaras c ON c.id = e.camara_id
           WHERE e.detectado_en LIKE ?
           GROUP BY c.estacion ORDER BY eventos DESC LIMIT 5''',
        (f'{hoy}%',)
    ).fetchall()

    conn.close()
    return jsonify({
        'fecha':          hoy,
        'total_hoy':      len(eventos),
        'por_hora':       [dict(r) for r in por_hora],
        'top_estaciones': [dict(r) for r in top_estaciones],
        'eventos':        [dict(r) for r in eventos],
    })


# ── GET /api/stats/auditoria ──────────────────────────
@stats_bp.route('/auditoria', methods=['GET'])
@requiere_auth
@requiere_permiso('auditoria:ver')
def auditoria():
    limite = min(int(request.args.get('limite', 100)), 500)
    conn   = get_conn()
    rows   = conn.execute(
        '''SELECT a.id, a.accion, a.detalle, a.ip_origen, a.fecha,
                  u.username, u.nombre, u.rol
           FROM auditoria a
           LEFT JOIN usuarios u ON u.id = a.usuario_id
           ORDER BY a.fecha DESC LIMIT ?''',
        (limite,)
    ).fetchall()
    conn.close()
    return jsonify({'total': len(rows), 'registros': [dict(r) for r in rows]})
