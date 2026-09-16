"""
routes/auth.py
──────────────
POST /api/auth/login    → Iniciar sesión
POST /api/auth/logout   → Cerrar sesión
GET  /api/auth/me       → Usuario actual
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify
from services.auth_service import (
    hash_password, verify_password, create_session, validate_token,
    revoke_token, requiere_auth, registrar_auditoria
)
from utils.limiter import limiter
from utils.validators import validate_email, validate_password, validate_avatar, format_error

auth_bp = Blueprint('auth', __name__)
DB_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── POST /api/auth/registro ───────────────────────────────
@auth_bp.route('/registro', methods=['POST'])
@limiter.limit("5 per minute")
def registro():
    """
    Registro público - el usuario nace con activo=0 (pendiente de aprobación admin).
    Body JSON: { nombre, username, password, rol, avatar_url (opcional) }
    """
    data     = request.get_json(silent=True) or {}
    nombre   = data.get('nombre', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    rol      = data.get('rol', '').strip()
    email    = data.get('email', '').strip() or f"{username}@argos.local"
    avatar   = data.get('avatar_url', '')

    ROLES_VALIDOS = ('supervisor','operador','analista','tecnico')   # admin y auditor no son registrables públicamente

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
            return jsonify({'error': f'El nombre de usuario "{username}" ya está en uso.'}), 409

        conn.execute(
            '''INSERT INTO usuarios (username, password, nombre, email, rol, activo, avatar_url)
               VALUES (?, ?, ?, ?, ?, 0, ?)''',
            (username, hash_password(password), nombre, email, rol, avatar)
        )
        conn.commit()
        registrar_auditoria(None, 'REGISTRO_PUBLICO', f'Nuevo usuario pendiente: {username} (rol: {rol})')
        return jsonify({'mensaje': 'Cuenta creada. Un administrador debe aprobarla antes de que puedas iniciar sesión.'}), 201
    except Exception:
        conn.rollback()
        return jsonify({'error': 'Error interno del servidor. Por favor, intenta de nuevo.'}), 500
    finally:
        conn.close()


# ── POST /api/auth/login ──────────────────────────────
@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    """
    Body JSON: { "usuario": "...", "password": "...", "rol": "..." }
    Si 2FA activo: { "2fa_requerido": true, "token_temp": "..." }
    Sino:          { "token": "...", "usuario": {...} }
    """
    data = request.get_json(silent=True) or {}
    username = data.get('usuario', '').strip()
    password = data.get('password', '').strip()
    rol_solicitado = data.get('rol', '').strip()

    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña son obligatorios.'}), 400

    conn = get_conn()
    user = conn.execute(
        'SELECT * FROM usuarios WHERE username = ? AND activo = 1',
        (username,)
    ).fetchone()
    conn.close()

    if not user or not verify_password(password, user['password']):
        registrar_auditoria(None, 'LOGIN_FALLIDO', f'Intento fallido: {username} desde {request.remote_addr}')
        return jsonify({'error': 'Credenciales incorrectas.'}), 401

    if rol_solicitado and user['rol'] != rol_solicitado:
        return jsonify({'error': f'El usuario "{username}" tiene rol "{user["rol"]}", no "{rol_solicitado}".'}), 403

    # ── 2FA: si está activo, emitir token temporal ────────────────────────
    try:
        fa2 = user['fa2_activo']
    except (IndexError, KeyError):
        fa2 = 0

    if fa2:
        temp_token = create_session(user['id'])
        return jsonify({
            'status':         '2fa_requerido',
            '2fa_requerido':  True,
            'token_temp':     temp_token,
            'username':       user['username'],
        })

    token = create_session(user['id'])
    registrar_auditoria(user['id'], 'LOGIN', f'Inicio de sesión desde {request.remote_addr}')

    return jsonify({
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
@auth_bp.route('/login-2fa', methods=['POST'])
@limiter.limit("5 per minute")
def login_2fa():
    """
    Body: { "token_temp": "...", "codigo": "123456" }
    Valida TOTP o backup code. Devuelve token definitivo.
    """
    data       = request.get_json(silent=True) or {}
    token_temp = data.get('token_temp', '').strip()
    codigo     = str(data.get('codigo', '')).strip()

    if not token_temp or not codigo:
        return jsonify({'error': 'token_temp y codigo son obligatorios.'}), 400

    usuario = validate_token(token_temp)
    if not usuario:
        return jsonify({'error': 'Token temporal inválido o expirado.'}), 401

    conn = get_conn()
    user = conn.execute('SELECT * FROM usuarios WHERE id=?', (usuario['id'],)).fetchone()

    try:
        fa2 = user['fa2_activo']
    except (IndexError, KeyError):
        fa2 = 0

    if not user or not fa2:
        conn.close()
        return jsonify({'error': 'El usuario no tiene 2FA activo.'}), 400

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
            return jsonify({'error': 'Código incorrecto.'}), 400

    except Exception as e:
        conn.close()
        return jsonify({'error': f'Error de 2FA: {str(e)}'}), 500

    revoke_token(token_temp)
    token = create_session(user['id'])
    registrar_auditoria(user['id'], 'LOGIN_2FA', f'Login con 2FA desde {request.remote_addr}')
    conn.close()

    return jsonify({
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
@auth_bp.route('/logout', methods=['POST'])
@requiere_auth
def logout():
    token = request.headers.get('X-Token') or request.args.get('token')
    registrar_auditoria(request.usuario['id'], 'LOGOUT', 'Cierre de sesión')
    revoke_token(token)
    return jsonify({'status': 'ok', 'mensaje': 'Sesión cerrada correctamente.'})


# ── GET /api/auth/me ──────────────────────────────────
@auth_bp.route('/me', methods=['GET'])
@requiere_auth
def me():
    """Devuelve los datos del usuario autenticado."""
    return jsonify({'usuario': request.usuario})
