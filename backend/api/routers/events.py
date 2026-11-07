"""
api/routers/events.py
────────────────────────────────────
GET  /api/eventos                  → Lista eventos
POST /api/eventos                  → Registrar evento
GET  /api/eventos/<id>             → Detalle
PUT  /api/eventos/<id>/estado      → Confirmar / descartar
GET  /api/eventos/pendientes       → Solo pendientes
"""

import sqlite3
import os
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from services.auth_service import (
    registrar_auditoria, get_current_user,
    require_permission,
)

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
def list_events(
    request: Request,
    estado: str = None,
    tipo: str = None,
    estacion: str = None,
    limite: int = 50,
    pagina: int = 1,
    usuario: dict = Depends(require_permission("eventos:ver")),
):
    limite = min(limite, 200)
    pagina = max(pagina, 1)
    offset = (pagina - 1) * limite

    query = '''
        SELECT e.id, e.tipo, e.confianza, e.estado, e.observaciones,
               e.evidencia, e.detectado_en, e.revisado_en,
               c.codigo as camara_codigo, c.estacion, c.ubicacion,
               u.nombre as operador_nombre
        FROM eventos e
        JOIN camaras c ON c.id = e.camara_id
        LEFT JOIN usuarios u ON u.id = e.operador_id
        WHERE 1=1
    '''
    params = []
    if estado:
        query += ' AND e.estado = ?'; params.append(estado)
    if tipo:
        query += ' AND e.tipo = ?'; params.append(tipo)
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

    return JSONResponse(content={
        'total':   total,
        'pagina':  pagina,
        'limite':  limite,
        'eventos': [dict(r) for r in rows],
    })


@router.get("/pendientes")
def pending_events(usuario: dict = Depends(require_permission("eventos:ver"))):
    conn = get_conn()
    rows = conn.execute(
        '''SELECT e.id, e.tipo, e.confianza, e.evidencia, e.detectado_en,
                  c.codigo as camara_codigo, c.estacion, c.ubicacion
           FROM eventos e
           JOIN camaras c ON c.id = e.camara_id
           WHERE e.estado = 'pendiente'
           ORDER BY e.detectado_en DESC
           LIMIT 50'''
    ).fetchall()
    conn.close()
    return JSONResponse(content={'total': len(rows), 'eventos': [dict(r) for r in rows]})


@router.get("/{event_id}")
def get_event(event_id: int, usuario: dict = Depends(require_permission("eventos:ver_detalle"))):
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
        return JSONResponse(status_code=404, content={'error': 'Evento no encontrado.'})
    return JSONResponse(content=dict(row))


@router.post("")
async def create_event(request: Request, usuario: dict = Depends(require_permission("eventos:crear"))):
    data = await request.json()
    if not data.get('camara_id') or data.get('confianza') is None:
        return JSONResponse(status_code=400, content={'error': '"camara_id" y "confianza" son obligatorios.'})

    conn = get_conn()
    cursor = conn.execute(
        '''INSERT INTO eventos (camara_id, tipo, confianza, estado, evidencia, observaciones)
           VALUES (?, ?, ?, 'pendiente', ?, ?)''',
        (data['camara_id'], data.get('tipo', 'evasion'), data['confianza'],
         data.get('evidencia'), data.get('observaciones'))
    )
    conn.commit()
    ev = conn.execute('SELECT * FROM eventos WHERE id=?', (cursor.lastrowid,)).fetchone()
    conn.close()
    return JSONResponse(status_code=201, content=dict(ev))


@router.put("/{event_id}/estado")
async def update_event_status(
    event_id: int,
    request: Request,
    usuario: dict = Depends(require_permission("eventos:revisar")),
):
    data   = await request.json()
    estado = data.get('estado')
    if estado not in ('confirmado', 'descartado'):
        return JSONResponse(status_code=400, content={'error': 'Estado debe ser "confirmado" o "descartado".'})

    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn  = get_conn()
    ev    = conn.execute('SELECT id FROM eventos WHERE id=?', (event_id,)).fetchone()
    if not ev:
        conn.close()
        return JSONResponse(status_code=404, content={'error': 'Evento no encontrado.'})

    conn.execute(
        'UPDATE eventos SET estado=?, observaciones=?, operador_id=?, revisado_en=? WHERE id=?',
        (estado, data.get('observaciones', ''), usuario['id'], ahora, event_id)
    )
    conn.commit()
    updated = conn.execute('SELECT * FROM eventos WHERE id=?', (event_id,)).fetchone()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'EVENTO_REVISADO',
                        f'Evento {event_id} marcado como {estado}', ip)
    return JSONResponse(content=dict(updated))

# ── POST /api/eventos/{event_id}/escalar ─────────────────
def _ensure_escalamientos_table(conn):
    """Garantiza la existencia idempotente de la tabla de escalamientos."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS escalamientos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id   INTEGER NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
            motivo      TEXT    NOT NULL,
            creado_en   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)


@router.post("/{event_id}/escalar")
async def escalar_evento(
    event_id: int,
    request: Request,
    usuario: dict = Depends(require_permission("eventos:revisar")),
):
    """
    Escala internamente un evento a supervisión/seguridad.
    Requiere permiso 'eventos:revisar'. No altera el estado (confirmado/descartado/pendiente)
    del evento en sí, permitiendo una trazabilidad auditable independiente.
    Body JSON: { "motivo": "..." } (obligatorio, no vacío)
    """
    try:
        data = await request.json()
        if not isinstance(data, dict):
            return JSONResponse(status_code=400, content={'error': 'El cuerpo debe ser un objeto JSON.'})
    except Exception:
        return JSONResponse(status_code=400, content={'error': 'JSON malformado o inválido.'})

    motivo = str(data.get('motivo', '') or data.get('observaciones', '') or '').strip()
    if not motivo:
        return JSONResponse(
            status_code=400,
            content={'error': 'El motivo u observación de escalamiento es obligatorio.'}
        )

    conn = get_conn()
    try:
        _ensure_escalamientos_table(conn)
        ev = conn.execute('SELECT id, tipo, estado FROM eventos WHERE id = ?', (event_id,)).fetchone()
        if not ev:
            return JSONResponse(status_code=404, content={'error': 'Evento no encontrado.'})

        # Evitar escalamientos idénticos duplicados consecutivos si ya existe uno con mismo motivo en 5 min
        reciente = conn.execute(
            """SELECT id FROM escalamientos 
               WHERE evento_id = ? AND usuario_id = ? AND motivo = ?
                 AND creado_en >= datetime('now', '-5 minutes')""",
            (event_id, usuario['id'], motivo)
        ).fetchone()
        if reciente:
            return JSONResponse(
                status_code=409,
                content={'error': 'Este evento ya fue escalado recientemente con la misma justificación.'}
            )

        cur = conn.execute(
            """INSERT INTO escalamientos (evento_id, usuario_id, motivo)
               VALUES (?, ?, ?)""",
            (event_id, usuario['id'], motivo)
        )
        escalamiento_id = cur.lastrowid
        conn.commit()

        row = conn.execute(
            """SELECT esc.id, esc.evento_id, esc.usuario_id, esc.motivo, esc.creado_en,
                      u.username, u.nombre as usuario_nombre
               FROM escalamientos esc
               JOIN usuarios u ON u.id = esc.usuario_id
               WHERE esc.id = ?""",
            (escalamiento_id,)
        ).fetchone()

        ip = request.client.host if request.client else None
        registrar_auditoria(
            usuario['id'],
            'EVENTO_ESCALADO',
            f'Evento {event_id} escalado internamente a supervisión: {motivo[:60]}',
            ip
        )
        return JSONResponse(
            status_code=201,
            content={
                'mensaje': 'Alerta escalada internamente a supervisión con éxito.',
                'escalamiento': dict(row)
            }
        )
    except Exception:
        conn.rollback()
        return JSONResponse(status_code=500, content={'error': 'Error interno al registrar el escalamiento.'})
    finally:
        conn.close()


@router.get("/{event_id}/escalamientos")
def listar_escalamientos_evento(
    event_id: int,
    usuario: dict = Depends(require_permission("eventos:ver_detalle")),
):
    """Consulta el historial de escalamientos registrados para un evento."""
    conn = get_conn()
    try:
        _ensure_escalamientos_table(conn)
        ev = conn.execute('SELECT id FROM eventos WHERE id = ?', (event_id,)).fetchone()
        if not ev:
            return JSONResponse(status_code=404, content={'error': 'Evento no encontrado.'})

        rows = conn.execute(
            """SELECT esc.id, esc.evento_id, esc.usuario_id, esc.motivo, esc.creado_en,
                      u.username, u.nombre as usuario_nombre
               FROM escalamientos esc
               JOIN usuarios u ON u.id = esc.usuario_id
               WHERE esc.evento_id = ?
               ORDER BY esc.creado_en DESC""",
            (event_id,)
        ).fetchall()
        return JSONResponse(content={'total': len(rows), 'escalamientos': [dict(r) for r in rows]})
    finally:
        conn.close()
