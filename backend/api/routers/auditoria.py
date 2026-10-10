"""
api/routers/auditoria.py
────────────────────────────────────
GET /api/auditoria           → Log completo con filtros
GET /api/auditoria/stats     → Stats en tiempo real
GET /api/auditoria/export    → Descarga CSV
GET /api/auditoria/chart     → Actividad por hora (hoy)
"""

import sqlite3
import os
import csv
import io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Optional

from services.auth_service import require_permission

router = APIRouter()

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("")
def list_auditoria(
    q: Optional[str] = None,
    usuario_param: Optional[str] = None,
    fecha: Optional[str] = None,
    limite: int = 100,
    pagina: int = 1,
    usuario: dict = Depends(require_permission("auditoria:ver")),
):
    q       = (q or '').strip()
    u_param = (usuario_param or '').strip()
    fecha   = (fecha or '').strip()
    limite  = min(limite, 500)
    pagina  = max(pagina, 1)
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

    if u_param:
        base += ' AND u.username = ?'
        params.append(u_param)

    if fecha:
        base += ' AND a.fecha LIKE ?'
        params.append(f'{fecha}%')

    conn   = get_conn()
    total  = conn.execute(f'SELECT COUNT(*) FROM ({base})', params).fetchone()[0]
    rows   = conn.execute(
        base + f' ORDER BY a.fecha DESC LIMIT ? OFFSET ?', params + [limite, offset]
    ).fetchall()

    usuarios_unicos = conn.execute(
        'SELECT DISTINCT u.username FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id WHERE u.username IS NOT NULL ORDER BY u.username'
    ).fetchall()
    conn.close()

    return JSONResponse(content={
        'total':    total,
        'pagina':   pagina,
        'limite':   limite,
        'registros': [dict(r) for r in rows],
        'usuarios':  [r['username'] for r in usuarios_unicos],
    })


@router.get("/stats")
def auditoria_stats(usuario: dict = Depends(require_permission("auditoria:ver"))):
    conn = get_conn()
    now  = datetime.now()
    hoy  = now.strftime('%Y-%m-%d')
    h24  = (now - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    d7   = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    d30  = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

    total_hoy = conn.execute(
        "SELECT COUNT(*) FROM auditoria WHERE fecha LIKE ?", (f'{hoy}%',)
    ).fetchone()[0]
    fallidos_24h = conn.execute(
        "SELECT COUNT(*) FROM auditoria WHERE fecha >= ? AND accion IN ('LOGIN_FALLIDO','ACCESO_DENEGADO')",
        (h24,)
    ).fetchone()[0]
    cambios_config_7d = conn.execute(
        """SELECT COUNT(*) FROM auditoria WHERE fecha >= ?
           AND accion IN ('CONFIG_ACTUALIZADA','MODELO_ACTUALIZADO','UMBRAL_MODIFICADO',
                          'CAMARA_ACTUALIZADA','CAMARA_CREADA','CAMARA_ELIMINADA')""",
        (d7,)
    ).fetchone()[0]
    exportaciones_30d = conn.execute(
        "SELECT COUNT(*) FROM auditoria WHERE fecha >= ? AND accion LIKE 'EXPORT%'", (d30,)
    ).fetchone()[0]
    total_registros = conn.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0]
    conn.close()

    return JSONResponse(content={
        'total_hoy':        total_hoy,
        'fallidos_24h':     fallidos_24h,
        'cambios_config_7d': cambios_config_7d,
        'exportaciones_30d': exportaciones_30d,
        'total_registros':   total_registros,
    })


@router.get("/chart")
def auditoria_chart(usuario: dict = Depends(require_permission("auditoria:ver"))):
    hoy  = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    rows = conn.execute(
        """SELECT strftime('%H', fecha) as hora, COUNT(*) as total
           FROM auditoria WHERE fecha LIKE ?
           GROUP BY hora ORDER BY hora""",
        (f'{hoy}%',)
    ).fetchall()
    conn.close()
    return JSONResponse(content={'fecha': hoy, 'por_hora': [dict(r) for r in rows]})


@router.get("/export")
def export_auditoria(
    fecha: Optional[str] = None,
    limite: int = 1000,
    usuario: dict = Depends(require_permission("auditoria:exportar")),
):
    limite = min(limite, 5000)
    conn   = get_conn()
    query  = '''SELECT a.id, a.accion, a.detalle, a.ip_origen, a.fecha,
                       u.username, u.nombre, u.rol
                FROM auditoria a
                LEFT JOIN usuarios u ON u.id = a.usuario_id'''
    params = []
    if fecha:
        query += ' WHERE a.fecha LIKE ?'
        params.append(f'{fecha}%')
    query += f' ORDER BY a.fecha DESC LIMIT ?'
    params.append(limite)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['id', 'accion', 'detalle', 'ip_origen', 'fecha', 'username', 'nombre', 'rol'])
        for r in rows:
            writer.writerow([r['id'], r['accion'], r['detalle'], r['ip_origen'],
                             r['fecha'], r['username'], r['nombre'], r['rol']])
        yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="auditoria.csv"'}
    )
