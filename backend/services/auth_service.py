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

def create_session(usuario_id: int) -> str:
    token  = generate_token()
    expira = (datetime.now() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    conn   = get_conn()
    conn.execute(
        'INSERT INTO sesiones (token, usuario_id, expira_en) VALUES (?,?,?)',
        (token, usuario_id, expira)
    )
    conn.commit()
    conn.close()
    return token


def validate_token(token: str):
    if not token:
        return None
    conn  = get_conn()
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row   = conn.execute(
        '''SELECT u.id, u.username, u.nombre, u.email, u.rol, u.activo
           FROM sesiones s
           JOIN usuarios u ON u.id = s.usuario_id
           WHERE s.token = ? AND s.expira_en > ? AND u.activo = 1''',
        (token, ahora)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_token(token: str):
    conn = get_conn()
    conn.execute('DELETE FROM sesiones WHERE token = ?', (token,))
    conn.commit()
    conn.close()


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
          AND s.ultima_actividad >= datetime('now', '-30 minutes')
          AND s.token = (
              SELECT s2.token
              FROM sesiones s2
              WHERE s2.usuario_id = s.usuario_id
                AND s2.expira_en > ?
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
