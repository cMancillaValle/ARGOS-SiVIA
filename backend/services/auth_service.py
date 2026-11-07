"""
services/auth_service.py  (migrado a FastAPI — sin imports Flask)
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Autenticación + integración RBAC

Exporta todos los símbolos originales para que los routers existentes
no necesiten cambiar sus imports, más las dependencias FastAPI nuevas
(get_current_user, require_permission, etc.).
"""

import sqlite3
import hashlib
import secrets
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

# Re-exportar el RBAC completo desde un solo punto de entrada
from services.rbac import (          # noqa: F401  (re-export)
    PERMISOS,
    PERMISOS_ROL,
    tiene_permiso,
    obtener_permisos,
    puede_acceder_modulo,
    requiere_permiso,
    requiere_cualquier_permiso,
)

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def hash_password(plain: str) -> str:
    """Utiliza werkzeug (PBKDF2/scrypt) en reemplazo del antiguo SHA-256."""
    return generate_password_hash(plain)

def verify_password(plain: str, stored_hash: str) -> bool:
    """Verifica passwords. Forma retrocompatible con los hashes antiguos SHA-256."""
    if stored_hash.startswith("pbkdf2:") or stored_hash.startswith("scrypt:"):
        return check_password_hash(stored_hash, plain)
    # Retrocompatibilidad con SHA-256 clásico
    return hashlib.sha256(plain.encode()).hexdigest() == stored_hash


def generate_token() -> str:
    return secrets.token_hex(32)


# ── Sesiones ──────────────────────────────────────────────────

def _get_session_ttl_minutes(conn=None) -> int:
    """Lee el TTL para sesiones nuevas; tolera instalaciones sin tabla de configuración."""
    owns_connection = conn is None
    db = conn or get_conn()
    try:
        row = db.execute(
            "SELECT valor FROM configuracion WHERE clave = 'session_ttl' LIMIT 1"
        ).fetchone()
        value = int(row['valor']) if row else 480
        return value if 30 <= value <= 1440 else 480
    except (sqlite3.Error, TypeError, ValueError, KeyError, IndexError):
        return 480
    finally:
        if owns_connection:
            db.close()

def create_session(usuario_id: int) -> str:
    token  = generate_token()
    conn   = get_conn()
    ttl_minutes = _get_session_ttl_minutes(conn)
    expira = (datetime.now() + timedelta(minutes=ttl_minutes)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        'INSERT INTO sesiones (token, usuario_id, expira_en, es_temporal) VALUES (?,?,?,0)',
        (token, usuario_id, expira)
    )
    conn.commit()
    conn.close()
    return token


def create_temp_2fa_session(usuario_id: int, minutos: int = 5) -> str:
    """
    Crea un token temporal exclusivo para el paso de verificación 2FA.
    Expira en 5 minutos y no autoriza endpoints normales.
    """
    token  = generate_token()
    expira = (datetime.now() + timedelta(minutes=minutos)).strftime('%Y-%m-%d %H:%M:%S')
    conn   = get_conn()
    conn.execute(
        'INSERT INTO sesiones (token, usuario_id, expira_en, es_temporal) VALUES (?,?,?,1)',
        (token, usuario_id, expira)
    )
    conn.commit()
    conn.close()
    return token


def validate_token(token: str):
    """
    Valida tokens de sesión normal. Rechaza tokens inexistentes, expirados,
    de usuarios inactivos o tokens temporales pendientes de 2FA.
    """
    if not token:
        return None
    conn  = get_conn()
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row   = conn.execute(
        '''SELECT u.id, u.username, u.nombre, u.email, u.rol, u.activo
           FROM sesiones s
           JOIN usuarios u ON u.id = s.usuario_id
           WHERE s.token = ? AND s.expira_en > ? AND u.activo = 1
             AND (s.es_temporal = 0 OR s.es_temporal IS NULL)''',
        (token, ahora)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def validate_temp_2fa_token(token: str):
    """
    Valida exclusivamente tokens temporales para el endpoint /api/auth/login-2fa.
    Rechaza tokens normales, expirados o de usuarios inactivos.
    """
    if not token:
        return None
    conn  = get_conn()
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row   = conn.execute(
        '''SELECT u.id, u.username, u.nombre, u.email, u.rol, u.activo
           FROM sesiones s
           JOIN usuarios u ON u.id = s.usuario_id
           WHERE s.token = ? AND s.expira_en > ? AND u.activo = 1
             AND s.es_temporal = 1''',
        (token, ahora)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_token(token: str):
    conn = get_conn()
    conn.execute('DELETE FROM sesiones WHERE token = ?', (token,))
    conn.commit()
    conn.close()


def revoke_all_user_sessions(usuario_id: int):
    """
    Invalida y elimina todas las sesiones (ordinarias y temporales)
    de un usuario especifico, y revoca sus tickets efimeros de streaming.
    """
    conn = get_conn()
    conn.execute('DELETE FROM sesiones WHERE usuario_id = ?', (usuario_id,))
    conn.commit()
    conn.close()
    try:
        revoke_stream_tickets_for_user(usuario_id)
    except Exception:
        pass


# ── Auditoría (sin depender de request Flask) ─────────────────

def registrar_auditoria(usuario_id, accion, detalle=None, ip: str = None):
    """
    Registra una acción en el log de auditoría.
    ip es opcional; si no se pasa, queda NULL en la BD.
    """
    try:
        conn = get_conn()
        conn.execute(
            'INSERT INTO auditoria (usuario_id, accion, detalle, ip_origen) VALUES (?,?,?,?)',
            (usuario_id, accion, detalle, ip)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Sesiones activas ──────────────────────────────────────────

def actualizar_modulo_sesion(token: str, modulo: str):
    if not token or not modulo:
        return False
    conn = get_conn()
    cur = conn.execute(
        '''UPDATE sesiones
           SET modulo_actual = ?, ultima_actividad = datetime('now')
           WHERE token = ?''',
        (modulo, token)
    )
    actualizado = cur.rowcount > 0
    conn.commit()
    conn.close()
    return actualizado


def listar_sesiones_activas():
    conn  = get_conn()
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    query = '''
        SELECT u.id AS usuario_id, u.username, u.nombre, u.rol,
               s.modulo_actual, s.creado_en AS conectado_desde,
               s.ultima_actividad
        FROM sesiones s
        JOIN usuarios u ON u.id = s.usuario_id
        WHERE s.expira_en > ?
          AND u.activo = 1
          AND (s.es_temporal = 0 OR s.es_temporal IS NULL)
          AND s.ultima_actividad >= datetime('now', '-30 minutes')
          AND s.token = (
              SELECT s2.token
              FROM sesiones s2
              WHERE s2.usuario_id = s.usuario_id
                AND s2.expira_en > ?
                AND (s2.es_temporal = 0 OR s2.es_temporal IS NULL)
              ORDER BY s2.ultima_actividad DESC, s2.creado_en DESC
              LIMIT 1
          )
        ORDER BY s.ultima_actividad DESC
    '''
    rows = conn.execute(query, (ahora, ahora)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ════════════════════════════════════════════════════════════════
# DEPENDENCIAS FASTAPI
# ════════════════════════════════════════════════════════════════

from fastapi import Header, HTTPException, Request, Depends
from typing import Optional


def get_current_user(x_token: Optional[str] = Header(default=None, alias="X-Token")):
    """
    Dependencia FastAPI: extrae y valida el token del header X-Token.
    Devuelve el dict del usuario si es válido, o lanza HTTP 401.
    """
    if not x_token:
        raise HTTPException(status_code=401, detail="No autorizado. Token inválido o expirado.")
    user = validate_token(x_token)
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado. Token inválido o expirado.")
    return user


def require_permission(permiso: str):
    """
    Dependencia FastAPI: verifica que el usuario tenga un permiso específico.

    Uso:
        @router.get("/endpoint")
        def endpoint(usuario = Depends(require_permission("camaras:ver"))):
            ...
    """
    def _check(usuario: dict = Depends(get_current_user)):
        if not tiene_permiso(usuario, permiso):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Acceso denegado.",
                    "detalle": f"Tu rol '{usuario.get('rol')}' no tiene el permiso '{permiso}'.",
                    "permiso_requerido": permiso,
                }
            )
        return usuario
    return _check


def require_any_permission(*permisos: str):
    """
    Dependencia FastAPI: pasa si el usuario tiene AL MENOS UNO de los permisos dados.
    """
    def _check(usuario: dict = Depends(get_current_user)):
        if not any(tiene_permiso(usuario, p) for p in permisos):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Acceso denegado.",
                    "detalle": f"Se requiere uno de: {', '.join(permisos)}",
                }
            )
        return usuario
    return _check


def require_role(*roles: str):
    """
    Dependencia FastAPI: verifica que el usuario tenga uno de los roles dados.
    """
    def _check(usuario: dict = Depends(get_current_user)):
        if usuario.get("rol") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Acceso denegado. Roles permitidos: {', '.join(roles)}"
            )
        return usuario
    return _check


# ── Compat: Stubs de decoradores Flask (NO usados en FastAPI) ──
# Mantenidos para que old routes/blueprint code sin migrar no explote al importar.

def requiere_auth(f):
    """
    STUB DE COMPATIBILIDAD — No usar en rutas FastAPI nuevas.
    En FastAPI, usar Depends(get_current_user).
    """
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        raise RuntimeError(
            "requiere_auth (Flask) no debe usarse en FastAPI. "
            "Usa Depends(get_current_user)."
        )
    return decorated


def requiere_rol(*roles):
    """STUB DE COMPATIBILIDAD — No usar en rutas FastAPI."""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated(*args, **kwargs):
            raise RuntimeError("requiere_rol (Flask) no debe usarse en FastAPI.")
        return decorated
    return decorator


# ════════════════════════════════════════════════════════════════
# TICKETS EFÍMEROS DE STREAMING (Corta duración, alcance restringido)
# ════════════════════════════════════════════════════════════════
import time
import threading

_stream_tickets = {}
_stream_tickets_lock = threading.Lock()
_sse_tickets = {}
_sse_tickets_lock = threading.Lock()


def issue_stream_ticket(
    user_id: int,
    cam_id: int,
    ttl_seconds: int = 45,
    session_token: str = None,
) -> str:
    """
    Genera un ticket criptográfico temporal de un solo propósito para reproducir
    el stream MJPEG de una cámara específica.
    """
    ticket = secrets.token_urlsafe(32)
    ahora = time.time()
    with _stream_tickets_lock:
        expirados = [t for t, data in _stream_tickets.items() if data['expira_en'] < ahora]
        for t in expirados:
            _stream_tickets.pop(t, None)

        _stream_tickets[ticket] = {
            'user_id': user_id,
            'cam_id': cam_id,
            'expira_en': ahora + ttl_seconds,
            'creado_en': ahora,
            'session_token': session_token,
        }
    return ticket


def validate_stream_ticket(ticket: str, cam_id: int):
    """
    Valida un ticket temporal de streaming para una cámara específica.
    Comprueba existencia, vigencia y si el usuario correspondiente
    aún tiene sesión activa y no ha sido desactivado.
    """
    if not ticket:
        return None

    ahora = time.time()
    with _stream_tickets_lock:
        data = _stream_tickets.get(ticket)
        if not data:
            return None
        if data['expira_en'] < ahora:
            _stream_tickets.pop(ticket, None)
            return None
        if data['cam_id'] != cam_id:
            return None

    conn = get_conn()
    row = conn.execute(
        'SELECT id, username, rol, activo FROM usuarios WHERE id = ? AND activo = 1',
        (data['user_id'],)
    ).fetchone()
    conn.close()

    if not row:
        return None

    if data.get('session_token') and not validate_token(data['session_token']):
        return None

    return dict(row)


def issue_sse_ticket(user_id: int, session_token: str, ttl_seconds: int = 90) -> str:
    """Emite una credencial corta y exclusiva para abrir el canal SSE de eventos."""
    ticket = secrets.token_urlsafe(32)
    now = time.time()
    with _sse_tickets_lock:
        expired = [t for t, data in _sse_tickets.items() if data['expira_en'] < now]
        for old in expired:
            _sse_tickets.pop(old, None)
        _sse_tickets[ticket] = {
            'user_id': user_id,
            'session_token': session_token,
            'expira_en': now + ttl_seconds,
        }
    return ticket


def validate_sse_ticket(ticket: str):
    """Valida alcance, vigencia y sesión emisora de un ticket SSE."""
    if not ticket:
        return None
    now = time.time()
    with _sse_tickets_lock:
        data = _sse_tickets.get(ticket)
        if not data:
            return None
        if data['expira_en'] < now:
            _sse_tickets.pop(ticket, None)
            return None
        session_token = data['session_token']
        expected_user_id = data['user_id']
    user = validate_token(session_token)
    if not user or user['id'] != expected_user_id:
        return None
    return user


def revoke_stream_tickets_for_user(user_id: int):
    """Revoca inmediatamente todos los tickets de streaming de un usuario."""
    with _stream_tickets_lock:
        a_eliminar = [t for t, data in _stream_tickets.items() if data['user_id'] == user_id]
        for t in a_eliminar:
            _stream_tickets.pop(t, None)
    with _sse_tickets_lock:
        a_eliminar = [t for t, data in _sse_tickets.items() if data['user_id'] == user_id]
        for t in a_eliminar:
            _sse_tickets.pop(t, None)
