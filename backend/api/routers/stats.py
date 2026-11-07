"""
api/routers/stats.py
────────────────────────────────────
GET /api/stats         → Resumen general
GET /api/stats/hoy     → Actividad últimas 24h
GET /api/stats/auditoria → Log de acciones
"""

import sqlite3
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from services.auth_service import get_current_user, require_permission

router = APIRouter()

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


@router.get("")
def general_stats(usuario: dict = Depends(get_current_user)):
    conn = get_conn()

    cam_total  = conn.execute('SELECT COUNT(*) FROM camaras').fetchone()[0]
    cam_activa = conn.execute('SELECT COUNT(*) FROM camaras WHERE estado="activa"').fetchone()[0]
    cam_offline= conn.execute('SELECT COUNT(*) FROM camaras WHERE estado="offline"').fetchone()[0]
    cam_mant   = conn.execute('SELECT COUNT(*) FROM camaras WHERE estado="mantenimiento"').fetchone()[0]

    ev_total   = conn.execute('SELECT COUNT(*) FROM eventos').fetchone()[0]
    ev_pend    = conn.execute('SELECT COUNT(*) FROM eventos WHERE estado="pendiente"').fetchone()[0]
    ev_confirm = conn.execute('SELECT COUNT(*) FROM eventos WHERE estado="confirmado"').fetchone()[0]
    ev_desc    = conn.execute('SELECT COUNT(*) FROM eventos WHERE estado="descartado"').fetchone()[0]

    hoy = datetime.now().strftime('%Y-%m-%d')
    ev_hoy  = conn.execute(
        'SELECT COUNT(*) FROM eventos WHERE detectado_en LIKE ?', (f'{hoy}%',)
    ).fetchone()[0]

    hace_48h = (datetime.now() - timedelta(hours=48)).strftime('%Y-%m-%d %H:%M:%S')
    por_hora = conn.execute(
        '''SELECT strftime('%Y-%m-%d %H:00', detectado_en) as hora, COUNT(*) as total
           FROM eventos WHERE detectado_en >= ?
           GROUP BY hora ORDER BY hora''',
        (hace_48h,)
    ).fetchall()

    usuarios = conn.execute('SELECT COUNT(*) FROM usuarios WHERE activo=1').fetchone()[0]

    # F24: Tasa de confirmación de eventos revisados por operadores humanos
    tasa_confirmacion = None
    if (ev_confirm + ev_desc) > 0:
        tasa_confirmacion = round(ev_confirm / (ev_confirm + ev_desc), 4)

    # Uptime real del host si psutil está disponible
    uptime_h = None
    try:
        import psutil
        boot = psutil.boot_time()
        uptime_h = round((datetime.now().timestamp() - boot) / 3600.0, 1)
    except Exception:
        uptime_h = None

    # FPS promedio configurado en cámaras activas
    fps_row = conn.execute('SELECT AVG(fps) FROM camaras WHERE estado="activa"').fetchone()
    fps_promedio = round(fps_row[0], 1) if fps_row and fps_row[0] is not None else None

    # Distribución real de eventos por estación
    estaciones_stats = conn.execute('''
        SELECT c.estacion, COUNT(e.id) as total
        FROM eventos e
        JOIN camaras c ON c.id = e.camara_id
        GROUP BY c.estacion
        ORDER BY total DESC
        LIMIT 6
    ''').fetchall()

    conn.close()
    return JSONResponse(content={
        'camaras': {
            'total': cam_total, 'activas': cam_activa,
            'offline': cam_offline, 'mantenimiento': cam_mant,
        },
        'eventos': {
            'total': ev_total, 'pendientes': ev_pend,
            'confirmados': ev_confirm, 'descartados': ev_desc, 'hoy': ev_hoy,
        },
        'sistema': {
            'usuarios_activos': usuarios,
            'tasa_confirmacion_operador': tasa_confirmacion,
            'precision_modelo': None,  # F24: Retirado 98% ficticio. No evaluado
            'precision_modelo_estado': 'no_evaluado',
            'fps_promedio': fps_promedio,
            'uptime_horas': uptime_h,
        },
        'actividad_48h': [dict(r) for r in por_hora],
        'por_estacion': [dict(r) for r in estaciones_stats],
    })


@router.get("/hoy")
def stats_today(usuario: dict = Depends(get_current_user)):
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

    por_hora = conn.execute(
        '''SELECT strftime('%H', detectado_en) as hora, COUNT(*) as total
           FROM eventos WHERE detectado_en LIKE ?
           GROUP BY hora ORDER BY hora''',
        (f'{hoy}%',)
    ).fetchall()

    top_estaciones = conn.execute(
        '''SELECT c.estacion, COUNT(*) as eventos
           FROM eventos e JOIN camaras c ON c.id = e.camara_id
           WHERE e.detectado_en LIKE ?
           GROUP BY c.estacion ORDER BY eventos DESC LIMIT 5''',
        (f'{hoy}%',)
    ).fetchall()

    conn.close()
    return JSONResponse(content={
        'fecha':          hoy,
        'total_hoy':      len(eventos),
        'por_hora':       [dict(r) for r in por_hora],
        'top_estaciones': [dict(r) for r in top_estaciones],
        'eventos':        [dict(r) for r in eventos],
    })


@router.get("/auditoria")
def auditoria(limite: int = 100, usuario: dict = Depends(require_permission("auditoria:ver"))):
    limite = min(limite, 500)
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
    return JSONResponse(content={'registros': [dict(r) for r in rows]})
