"""
routes/profile.py
─────────────────
Endpoints del perfil del usuario autenticado.

GET    /api/perfil/me                   → Datos del usuario actual
PUT    /api/perfil/me                   → Actualizar nombre
PUT    /api/perfil/me/avatar            → Cambiar avatar (base64)
POST   /api/perfil/me/email/solicitar   → Paso 1: verificar password, enviar código al email actual
POST   /api/perfil/me/email/confirmar   → Paso 2: verificar código 1, enviar código al nuevo email
POST   /api/perfil/me/email/finalizar   → Paso 3: verificar código 2, actualizar email
PUT    /api/perfil/me/password          → Cambiar contraseña (requiere actual)
POST   /api/perfil/me/2fa/activar       → Generar secret TOTP y URI de QR
POST   /api/perfil/me/2fa/confirmar     → Validar código, activar 2FA, devolver backup codes
POST   /api/perfil/me/2fa/desactivar    → Desactivar 2FA (requiere password + código TOTP)
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify
from services.auth_service import (
    hash_password, verify_password, requiere_auth, registrar_auditoria,
)
from utils.validators import validate_email, validate_password, validate_avatar, format_error
from services.two_factor import (
    generate_totp_secret, totp_qr_base64, verify_totp,
    encrypt_secret, decrypt_secret,
    generate_backup_codes, verify_backup_code,
    serialize_backup_codes, deserialize_backup_codes,
    check_availability as tf_check,
)
from services.email_service import (
    store_code, validate_code, peek_code,
    enviar_codigo_cambio_email,
)

profile_bp = Blueprint('profile', __name__)
DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns():
    """Agrega columnas nuevas de forma segura (idempotente)."""
    conn = get_conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(usuarios)")}
    alterations = {
        'avatar_url':    'TEXT DEFAULT NULL',
        'totp_secret':   'TEXT DEFAULT NULL',
        'fa2_activo':    'INTEGER NOT NULL DEFAULT 0',
        'backup_codes':  'TEXT DEFAULT NULL',
        'email_pending': 'TEXT DEFAULT NULL',
    }
    for col, definition in alterations.items():
        if col not in cols:
            conn.execute(f'ALTER TABLE usuarios ADD COLUMN {col} {definition}')
    conn.commit()
    conn.close()


# Asegurar columnas al importar el módulo
try:
    _ensure_columns()
except Exception:
    pass  # Se reintentará en el primer request


def _get_user(user_id: int):
    conn = get_conn()
    user = conn.execute('SELECT * FROM usuarios WHERE id=?', (user_id,)).fetchone()
    conn.close()
    return user


# ── GET /api/perfil/me ────────────────────────────────────────────────────
@profile_bp.route('/me', methods=['GET'])
@requiere_auth
def get_me():
    _ensure_columns()
    user = _get_user(request.usuario['id'])
    if not user:
        return jsonify({'error': 'Usuario no encontrado.'}), 404
    return jsonify({
        'id':          user['id'],
        'username':    user['username'],
        'nombre':      user['nombre'],
        'email':       user['email'],
        'rol':         user['rol'],
        'activo':      bool(user['activo']),
        'avatar_url':  user['avatar_url'],
        'fa2_activo':  bool(user['fa2_activo']),
        'creado_en':   user['creado_en'],
    })


# ── PUT /api/perfil/me ────────────────────────────────────────────────────
@profile_bp.route('/me', methods=['PUT'])
@requiere_auth
def update_me():
    data  = request.get_json(silent=True) or {}
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return jsonify({'error': 'El nombre no puede estar vacío.'}), 400
    conn = get_conn()
    conn.execute('UPDATE usuarios SET nombre=? WHERE id=?',
                 (nombre, request.usuario['id']))
    conn.commit()
    conn.close()
    registrar_auditoria(request.usuario['id'], 'PERFIL_ACTUALIZADO', 'Nombre actualizado')
    return jsonify({'status': 'ok', 'nombre': nombre})


# ── PUT /api/perfil/me/avatar ─────────────────────────────────────────────
@profile_bp.route('/me/avatar', methods=['PUT'])
@requiere_auth
def update_avatar():
    """Acepta { "avatar_url": "data:image/..." } o una URL."""
    data      = request.get_json(silent=True) or {}
    avatar_url = data.get('avatar_url', '').strip()
    if not avatar_url:
        return format_error('avatar_url es obligatorio.')
    
    if not validate_avatar(avatar_url):
        return format_error('Formato de avatar inválido o el tamaño excede el límite permitido.')
        
    conn = get_conn()
    conn.execute('UPDATE usuarios SET avatar_url=? WHERE id=?',
                 (avatar_url, request.usuario['id']))
    conn.commit()
    conn.close()
    registrar_auditoria(request.usuario['id'], 'AVATAR_ACTUALIZADO', 'Foto de perfil cambiada')
    return jsonify({'status': 'ok', 'avatar_url': avatar_url[:80] + '...'})


# ── POST /api/perfil/me/email/solicitar ──────────────────────────────────
@profile_bp.route('/me/email/solicitar', methods=['POST'])
@requiere_auth
def email_step1():
    """Verifica contraseña actual, envía código al email actual."""
    data     = request.get_json(silent=True) or {}
    password = data.get('password', '').strip()
    nuevo    = data.get('nuevo_email', '').strip()

    if not password or not nuevo:
        return format_error('password y nuevo_email son obligatorios.')

    if not validate_email(nuevo):
        return format_error('El formato de correo electrónico es inválido')

    user = _get_user(request.usuario['id'])
    if not user or not verify_password(password, user['password']):
        return jsonify({'error': 'Contraseña incorrecta.'}), 403

    if user['email'] == nuevo:
        return format_error('El nuevo email es igual al actual.')

    resultado = enviar_codigo_cambio_email(request.usuario['id'], user['email'], nuevo)
    respuesta = {'status': 'ok', 'mensaje': f'Código enviado a {user["email"]}.'}
    if resultado.get('dev'):
        respuesta['dev_code'] = resultado.get('code')
        respuesta['aviso']    = 'Modo desarrollo: código incluido en respuesta (configura SMTP en producción).'
    return jsonify(respuesta)


# ── POST /api/perfil/me/email/confirmar ──────────────────────────────────
@profile_bp.route('/me/email/confirmar', methods=['POST'])
@requiere_auth
def email_step2():
    """Verifica código 1 (email actual). Envía código al nuevo email."""
    data  = request.get_json(silent=True) or {}
    code  = str(data.get('codigo', '')).strip()
    uid   = request.usuario['id']

    ok, extra = validate_code('email_cambio', str(uid), code)
    if not ok:
        return jsonify({'error': 'Código incorrecto o expirado.'}), 400

    nuevo_email = extra.get('nuevo_email', '')
    if not nuevo_email:
        return jsonify({'error': 'Estado inválido. Inicia el proceso de nuevo.'}), 400

    resultado = enviar_codigo_cambio_email(uid, nuevo_email)
    respuesta = {'status': 'ok', 'mensaje': f'Código enviado a {nuevo_email}.'}
    if resultado.get('dev'):
        respuesta['dev_code'] = resultado.get('code')
        respuesta['aviso']    = 'Modo desarrollo: código incluido en respuesta.'
    return jsonify(respuesta)


# ── POST /api/perfil/me/email/finalizar ──────────────────────────────────
@profile_bp.route('/me/email/finalizar', methods=['POST'])
@requiere_auth
def email_step3():
    """Verifica código 2 (nuevo email) y actualiza el email en la BD."""
    data  = request.get_json(silent=True) or {}
    code  = str(data.get('codigo', '')).strip()
    nuevo = data.get('nuevo_email', '').strip()
    uid   = request.usuario['id']

    ok, _ = validate_code('email_nuevo', str(uid), code)
    if not ok:
        return jsonify({'error': 'Código incorrecto o expirado.'}), 400

    conn = get_conn()
    conn.execute('UPDATE usuarios SET email=? WHERE id=?', (nuevo, uid))
    conn.commit()
    conn.close()
    registrar_auditoria(uid, 'EMAIL_ACTUALIZADO', f'Nuevo email: {nuevo}')
    return jsonify({'status': 'ok', 'mensaje': 'Email actualizado correctamente.', 'nuevo_email': nuevo})


# ── PUT /api/perfil/me/password ──────────────────────────────────────────
@profile_bp.route('/me/password', methods=['PUT'])
@requiere_auth
def change_password_me():
    data       = request.get_json(silent=True) or {}
    actual     = data.get('actual', '').strip()
    nueva      = data.get('nueva', '').strip()
    confirmar  = data.get('confirmar', '').strip()
    uid        = request.usuario['id']

    if not actual or not nueva:
        return format_error('actual y nueva son obligatorios.')

    user = _get_user(uid)
    if not user or not verify_password(actual, user['password']):
        return jsonify({'error': 'Contraseña actual incorrecta.'}), 403

    if nueva != confirmar:
        return format_error('La nueva contraseña y su confirmación no coinciden.')

    # Validaciones de seguridad
    pass_ok, pass_msg = validate_password(nueva)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    conn = get_conn()
    conn.execute('UPDATE usuarios SET password=? WHERE id=?', (hash_password(nueva), uid))
    conn.commit()
    conn.close()
    registrar_auditoria(uid, 'PASSWORD_CAMBIADA', 'Contraseña actualizada desde perfil')
    return jsonify({'status': 'ok', 'mensaje': 'Contraseña actualizada correctamente.'})


# ── POST /api/perfil/me/2fa/activar ──────────────────────────────────────
@profile_bp.route('/me/2fa/activar', methods=['POST'])
@requiere_auth
def tfa_activar():
    """Genera secret TOTP y devuelve el URI QR para escanear."""
    avail = tf_check()
    if not avail['listo']:
        missing = [k for k, v in avail.items() if not v and k != 'listo']
        return jsonify({'error': f'2FA no disponible. Falta: {", ".join(missing)}. '
                                 'Instala: pip install pyotp qrcode[pil] cryptography '
                                 'y define ARGOS_FERNET_KEY en ENV.'}), 503

    uid  = request.usuario['id']
    user = _get_user(uid)
    if not user:
        return jsonify({'error': 'Usuario no encontrado.'}), 404

    if user['fa2_activo']:
        return jsonify({'error': '2FA ya está activo. Desactívalo primero.'}), 400

    secret         = generate_totp_secret()
    secret_cifrado = encrypt_secret(secret)
    qr_b64         = totp_qr_base64(secret, user['username'])

    # Guardar secret cifrado en BD (no activo aún hasta confirmar)
    conn = get_conn()
    conn.execute('UPDATE usuarios SET totp_secret=?, fa2_activo=0 WHERE id=?',
                 (secret_cifrado, uid))
    conn.commit()
    conn.close()

    return jsonify({
        'status':   'ok',
        'qr_image': qr_b64,
        'mensaje':  'Escanea el QR con Google Authenticator u otra app TOTP y luego confirma con un código.',
    })


# ── POST /api/perfil/me/2fa/confirmar ────────────────────────────────────
@profile_bp.route('/me/2fa/confirmar', methods=['POST'])
@requiere_auth
def tfa_confirmar():
    """Valida el primer código TOTP. Activa 2FA y genera backup codes."""
    data  = request.get_json(silent=True) or {}
    code  = str(data.get('codigo', '')).strip()
    uid   = request.usuario['id']
    user  = _get_user(uid)

    if not user or not user['totp_secret']:
        return jsonify({'error': 'No has iniciado el proceso de activación de 2FA.'}), 400
    if user['fa2_activo']:
        return jsonify({'error': '2FA ya está activo.'}), 400

    try:
        secret = decrypt_secret(user['totp_secret'])
    except ValueError:
        return jsonify({'error': 'Error al descifrar el secret TOTP.'}), 500

    if not verify_totp(secret, code):
        return jsonify({'error': 'Código incorrecto. Verifica que la hora de tu dispositivo sea correcta.'}), 400

    plain_codes, hashed_codes = generate_backup_codes()

    conn = get_conn()
    conn.execute('UPDATE usuarios SET fa2_activo=1, backup_codes=? WHERE id=?',
                 (serialize_backup_codes(hashed_codes), uid))
    conn.commit()
    conn.close()
    registrar_auditoria(uid, '2FA_ACTIVADO', 'Autenticación de dos factores activada')

    return jsonify({
        'status':       'ok',
        'mensaje':      '2FA activado correctamente.',
        'backup_codes': plain_codes,
        'aviso':        '⚠️ Guarda estos códigos en un lugar seguro. Solo se muestran una vez.',
    })


# ── POST /api/perfil/me/2fa/desactivar ───────────────────────────────────
@profile_bp.route('/me/2fa/desactivar', methods=['POST'])
@requiere_auth
def tfa_desactivar():
    """Desactiva 2FA. Requiere contraseña actual + código TOTP actual."""
    data     = request.get_json(silent=True) or {}
    password = data.get('password', '').strip()
    code     = str(data.get('codigo', '')).strip()
    uid      = request.usuario['id']
    user     = _get_user(uid)

    if not user:
        return jsonify({'error': 'Usuario no encontrado.'}), 404
    if not user['fa2_activo']:
        return format_error('2FA no está activo.')
    if not verify_password(password, user['password']):
        return jsonify({'error': 'Contraseña incorrecta.'}), 403

    try:
        secret = decrypt_secret(user['totp_secret'])
    except ValueError:
        return jsonify({'error': 'Error interno de 2FA.'}), 500

    if not verify_totp(secret, code):
        return jsonify({'error': 'Código TOTP incorrecto.'}), 400

    conn = get_conn()
    conn.execute('UPDATE usuarios SET fa2_activo=0, totp_secret=NULL, backup_codes=NULL WHERE id=?', (uid,))
    conn.commit()
    conn.close()
    registrar_auditoria(uid, '2FA_DESACTIVADO', 'Autenticación de dos factores desactivada')
    return jsonify({'status': 'ok', 'mensaje': '2FA desactivado correctamente.'})
