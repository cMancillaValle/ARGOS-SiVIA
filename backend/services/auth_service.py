"""
services/auth_service.py  (actualizado con RBAC)
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Autenticación + integración RBAC

Exporta todos los decoradores originales PLUS los nuevos
de rbac.py para que el resto del código no necesite
cambiar sus imports.
"""

import sqlite3
import hashlib
import secrets
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
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


# ── Decorador: autenticación ──────────────────────────────────

def requiere_auth(f):
    """Valida el token X-Token. Inyecta request.usuario."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('X-Token')
        user  = validate_token(token)
        if not user:
            return jsonify({'error': 'No autorizado. Token inválido o expirado.'}), 401
        request.usuario = user
        return f(*args, **kwargs)
    return decorated


# ── Decorador: rol(es) específico(s) ─────────────────────────
# Mantenido por compatibilidad con el código existente

def requiere_rol(*roles):
    """
    Acepta la request solo si el usuario tiene uno de los roles dados.
    Para nuevos endpoints prefer @requiere_permiso('modulo:accion').
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('X-Token')
            user  = validate_token(token)
            if not user:
                return jsonify({'error': 'No autorizado.'}), 401
            if user['rol'] not in roles:
                return jsonify({
                    'error': f'Acceso denegado. Roles permitidos: {", ".join(roles)}'
                }), 403
            request.usuario = user
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auditoría ─────────────────────────────────────────────────

def registrar_auditoria(usuario_id, accion, detalle=None):
    try:
        ip   = request.remote_addr if request else None
        conn = get_conn()
        conn.execute(
            'INSERT INTO auditoria (usuario_id, accion, detalle, ip_origen) VALUES (?,?,?,?)',
            (usuario_id, accion, detalle, ip)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
