"""
api/routers/auth.py
───────────────────────────────────────────
POST /api/auth/registro   → Registro público
POST /api/auth/login      → Iniciar sesión
POST /api/auth/login-2fa  → Verificar TOTP / backup code
POST /api/auth/logout     → Cerrar sesión
GET  /api/auth/me         → Usuario actual
"""

import sqlite3
import os
import logging
from fastapi import APIRouter, Request, Depends, Header
from fastapi.responses import JSONResponse
from typing import Optional

from services.auth_service import (
    hash_password, verify_password, create_session, validate_token,
    revoke_token, registrar_auditoria, get_current_user,
)
from utils.limiter import limiter
from utils.validators import validate_email, validate_password, validate_avatar, format_error

logger = logging.getLogger(__name__)
router = APIRouter()

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── POST /api/auth/registro ───────────────────────────────
@router.post("/registro")
@limiter.limit("5/minute")
def registro(request: Request):
    """
    Registro público - el usuario nace con activo=0 (pendiente de aprobación admin).
    Body JSON: { nombre, username, password, rol, avatar_url (opcional) }
    """
    import json
    try:
        data = request._json if hasattr(request, '_json') else {}
    except Exception:
        data = {}

    nombre   = data.get('nombre', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    rol      = data.get('rol', '').strip()
    email    = data.get('email', '').strip() or f"{username}@argos.local"
    avatar   = data.get('avatar_url', '')

    ROLES_VALIDOS = ('supervisor', 'operador', 'analista', 'tecnico')

    if not all([nombre, username, password, rol]):
        return format_error('Faltan campos obligatorios (nombre, username, password, rol).')
    if rol not in ROLES_VALIDOS:
        return format_error(f'Rol inválido. Opciones: {", ".join(ROLES_VALIDOS)}')
    if email and not validate_email(email):
        return format_error('El formato de correo electrónico es inválido')

    pass_ok, pass_msg = validate_password(password)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')
    if avatar and not validate_avatar(avatar):
        return format_error('URL de Avatar inválida o excede el tamaño permitido')

    conn = get_conn()
    try:
        existe = conn.execute('SELECT id FROM usuarios WHERE username = ?', (username,)).fetchone()
        if existe:
            return JSONResponse(
                status_code=409,
                content={'error': f'El nombre de usuario "{username}" ya está en uso.'}
            )
        conn.execute(
            '''INSERT INTO usuarios (username, password, nombre, email, rol, activo, avatar_url)
               VALUES (?, ?, ?, ?, ?, 0, ?)''',
            (username, hash_password(password), nombre, email, rol, avatar)
        )
        conn.commit()
        registrar_auditoria(None, 'REGISTRO_PUBLICO',
                            f'Nuevo usuario pendiente: {username} (rol: {rol})',
                            request.client.host if request.client else None)
        return JSONResponse(
            status_code=201,
            content={'mensaje': 'Cuenta creada. Un administrador debe aprobarla antes de que puedas iniciar sesión.'}
        )
    except Exception:
        conn.rollback()
        return JSONResponse(status_code=500, content={'error': 'Error interno del servidor. Por favor, intenta de nuevo.'})
    finally:
        conn.close()


# ── POST /api/auth/login ──────────────────────────────
@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request):
    """
    Body JSON: { "usuario": "...", "password": "...", "rol": "..." }
    """
    data = await request.json() if await _has_body(request) else {}
    username       = data.get('usuario', '').strip()
    password       = data.get('password', '').strip()
    rol_solicitado = data.get('rol', '').strip()

    if not username or not password:
        return JSONResponse(status_code=400, content={'error': 'Usuario y contraseña son obligatorios.'})

    conn = get_conn()
    user = conn.execute(
        'SELECT * FROM usuarios WHERE username = ? AND activo = 1', (username,)
    ).fetchone()
    conn.close()

    ip = request.client.host if request.client else None

    if not user or not verify_password(password, user['password']):
        registrar_auditoria(None, 'LOGIN_FALLIDO',
                            f'Intento fallido: {username} desde {ip}', ip)
        return JSONResponse(status_code=401, content={'error': 'Credenciales incorrectas.'})

    if rol_solicitado and user['rol'] != rol_solicitado:
        return JSONResponse(
            status_code=403,
            content={'error': f'El usuario "{username}" tiene rol "{user["rol"]}", no "{rol_solicitado}".'}
        )

    # ── 2FA ──────────────────────────────────────────────────
    try:
        fa2 = user['fa2_activo']
    except (IndexError, KeyError):
        fa2 = 0

    if fa2:
        temp_token = create_session(user['id'])
        return JSONResponse(content={
            'status': '2fa_requerido',
            '2fa_requerido': True,
            'token_temp': temp_token,
            'username': user['username'],
        })

    token = create_session(user['id'])
    registrar_auditoria(user['id'], 'LOGIN', f'Inicio de sesión desde {ip}', ip)

    return JSONResponse(content={
        'status': 'ok',
        'token': token,
        'usuario': {
            'id':       user['id'],
            'username': user['username'],
            'nombre':   user['nombre'],
            'email':    user['email'],
            'rol':      user['rol'],
        }
    })


# ── POST /api/auth/login-2fa ──────────────────────────
@router.post("/login-2fa")
@limiter.limit("5/minute")
async def login_2fa(request: Request):
    """
    Body: { "token_temp": "...", "codigo": "123456" }
    """
    data       = await request.json() if await _has_body(request) else {}
    token_temp = data.get('token_temp', '').strip()
    codigo     = str(data.get('codigo', '')).strip()

    if not token_temp or not codigo:
        return JSONResponse(status_code=400, content={'error': 'token_temp y codigo son obligatorios.'})

    usuario = validate_token(token_temp)
    if not usuario:
        return JSONResponse(status_code=401, content={'error': 'Token temporal inválido o expirado.'})

    conn = get_conn()
    user = conn.execute('SELECT * FROM usuarios WHERE id=?', (usuario['id'],)).fetchone()

    try:
        fa2 = user['fa2_activo']
    except (IndexError, KeyError):
        fa2 = 0

    if not user or not fa2:
        conn.close()
        return JSONResponse(status_code=400, content={'error': 'El usuario no tiene 2FA activo.'})

    try:
        from services.two_factor import (
            decrypt_secret, verify_totp, verify_backup_code,
            serialize_backup_codes, deserialize_backup_codes,
        )
        secret    = decrypt_secret(user['totp_secret'])
        totp_ok   = verify_totp(secret, codigo)
        backup_ok = False

        if not totp_ok:
            stored = deserialize_backup_codes(user['backup_codes'])
            backup_ok, remaining = verify_backup_code(codigo, stored)
            if backup_ok:
                conn.execute('UPDATE usuarios SET backup_codes=? WHERE id=?',
                             (serialize_backup_codes(remaining), user['id']))
                conn.commit()

        if not totp_ok and not backup_ok:
            conn.close()
            return JSONResponse(status_code=400, content={'error': 'Código incorrecto.'})

    except Exception as e:
        conn.close()
        return JSONResponse(status_code=500, content={'error': f'Error de 2FA: {str(e)}'})

    ip = request.client.host if request.client else None
    revoke_token(token_temp)
    token = create_session(user['id'])
    registrar_auditoria(user['id'], 'LOGIN_2FA', f'Login con 2FA desde {ip}', ip)
    conn.close()

    return JSONResponse(content={
        'status': 'ok',
        'token': token,
        'usuario': {
            'id':       user['id'],
            'username': user['username'],
            'nombre':   user['nombre'],
            'email':    user['email'],
            'rol':      user['rol'],
        }
    })


# ── POST /api/auth/logout ─────────────────────────────
@router.post("/logout")
async def logout(
    request: Request,
    usuario: dict = Depends(get_current_user),
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
):
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'LOGOUT', 'Cierre de sesión', ip)
    if x_token:
        revoke_token(x_token)
    return JSONResponse(content={'status': 'ok', 'mensaje': 'Sesión cerrada correctamente.'})


# ── GET /api/auth/me ──────────────────────────────────
@router.get("/me")
def me(usuario: dict = Depends(get_current_user)):
    return JSONResponse(content={'usuario': usuario})


# ── Helper ────────────────────────────────────────────
async def _has_body(request: Request) -> bool:
    """Devuelve True si el request tiene un body JSON legible."""
    body = await request.body()
    return bool(body)
