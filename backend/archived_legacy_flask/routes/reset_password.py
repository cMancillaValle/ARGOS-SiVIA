"""
routes/reset_password.py
──────────────────────────
Flujo de restablecimiento de contraseña sin autenticación.

POST /api/auth/reset-password/solicitar  → username/email → envía código
POST /api/auth/reset-password/confirmar  → código + nueva contraseña
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify
from services.auth_service import hash_password, registrar_auditoria
from services.email_service import (
    store_code, validate_code,
    enviar_codigo_reset_password,
)
from utils.limiter import limiter
from utils.validators import validate_password, format_error

reset_bp = Blueprint('reset_password', __name__)
DB_PATH  = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── POST /api/auth/reset-password/solicitar ──────────────────────────────
@reset_bp.route('/solicitar', methods=['POST'])
@limiter.limit("5 per minute")
def solicitar_reset():
    """
    Body: { "identificador": "username o email" }
    Busca el usuario, genera un código y lo envía al email registrado.
    """
    data   = request.get_json(silent=True) or {}
    ident  = data.get('identificador', '').strip()
    if not ident:
        return jsonify({'error': 'Proporciona tu usuario o email.'}), 400

    conn = get_conn()
    user = conn.execute(
        'SELECT * FROM usuarios WHERE (username=? OR email=?) AND activo=1',
        (ident, ident)
    ).fetchone()
    conn.close()

    # Por seguridad: siempre responder OK para no revelar si el usuario existe
    if not user:
        return jsonify({
            'status': 'ok',
            'mensaje': 'Si el usuario existe, recibirás un email con instrucciones.',
        })

    resultado = enviar_codigo_reset_password(user['email'], user['username'])

    respuesta = {
        'status':  'ok',
        'mensaje': f'Código enviado al email registrado de {user["username"]}.',
        'username': user['username'],
    }
    if resultado.get('dev'):
        respuesta['dev_code'] = resultado.get('code')
        respuesta['aviso']    = 'Modo desarrollo: SMTP no configurado. Código incluido en respuesta.'
    return jsonify(respuesta)


# ── POST /api/auth/reset-password/confirmar ───────────────────────────────
@reset_bp.route('/confirmar', methods=['POST'])
@limiter.limit("5 per minute")
def confirmar_reset():
    """
    Body: { "username": "...", "codigo": "123456", "nueva_password": "..." }
    """
    data     = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    code     = str(data.get('codigo', '')).strip()
    nueva    = data.get('nueva_password', '').strip()

    if not all([username, code, nueva]):
        return format_error('username, codigo y nueva_password son obligatorios.')

    # Validaciones de seguridad
    pass_ok, pass_msg = validate_password(nueva)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    ok, _ = validate_code('reset_pass', username, code)
    if not ok:
        return jsonify({'error': 'Código incorrecto o expirado. Solicita un nuevo código.'}), 400

    conn = get_conn()
    user = conn.execute('SELECT id FROM usuarios WHERE username=? AND activo=1', (username,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Usuario no encontrado.'}), 404

    conn.execute('UPDATE usuarios SET password=? WHERE id=?',
                 (hash_password(nueva), user['id']))
    conn.commit()
    conn.close()
    registrar_auditoria(user['id'], 'PASSWORD_RESET', 'Contraseña restablecida via email')
    return jsonify({'status': 'ok', 'mensaje': 'Contraseña restablecida. Ya puedes iniciar sesión.'})
