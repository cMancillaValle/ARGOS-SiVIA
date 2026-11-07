"""
api/routers/profile.py
────────────────────────────────────
GET    /api/perfil/me                   → Datos del usuario actual
PUT    /api/perfil/me                   → Actualizar nombre
PUT    /api/perfil/me/avatar            → Cambiar avatar (base64)
POST   /api/perfil/me/email/solicitar   → Verificar password y enviar código al email nuevo
POST   /api/perfil/me/email/confirmar   → Paso 2: verificar código 1, enviar código al nuevo email
POST   /api/perfil/me/email/finalizar   → Paso 3: verificar código 2, actualizar email
PUT    /api/perfil/me/password          → Cambiar contraseña (requiere actual)
POST   /api/perfil/me/2fa/activar       → Generar secret TOTP y URI de QR
POST   /api/perfil/me/2fa/confirmar     → Validar código, activar 2FA, devolver backup codes
POST   /api/perfil/me/2fa/desactivar    → Desactivar 2FA (requiere password + código TOTP)
"""

import sqlite3
import os
import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from services.auth_service import (
    hash_password, verify_password, get_current_user, registrar_auditoria,
    revoke_all_user_sessions,
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
from utils.limiter import limiter

router = APIRouter()
logger = logging.getLogger(__name__)
DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
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


try:
    _ensure_columns()
except Exception:
    pass


def _get_user(user_id: int):
    conn = get_conn()
    user = conn.execute('SELECT * FROM usuarios WHERE id=?', (user_id,)).fetchone()
    conn.close()
    return user


@router.get("/me")
def get_me(usuario: dict = Depends(get_current_user)):
    _ensure_columns()
    user = _get_user(usuario['id'])
    if not user:
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})
    return JSONResponse(content={
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


@router.put("/me")
async def update_me(request: Request, usuario: dict = Depends(get_current_user)):
    data   = await request.json() if await _has_body(request) else {}
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return JSONResponse(status_code=400, content={'error': 'El nombre no puede estar vacío.'})
    conn = get_conn()
    conn.execute('UPDATE usuarios SET nombre=? WHERE id=?', (nombre, usuario['id']))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'PERFIL_ACTUALIZADO', 'Nombre actualizado', ip)
    return JSONResponse(content={'status': 'ok', 'nombre': nombre})


@router.put("/me/avatar")
async def update_avatar(request: Request, usuario: dict = Depends(get_current_user)):
    data       = await request.json() if await _has_body(request) else {}
    avatar_url = data.get('avatar_url', '').strip()
    if not avatar_url:
        return format_error('avatar_url es obligatorio.')

    if not validate_avatar(avatar_url):
        return format_error('Formato de avatar inválido o el tamaño excede el límite permitido.')

    conn = get_conn()
    conn.execute('UPDATE usuarios SET avatar_url=? WHERE id=?', (avatar_url, usuario['id']))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'AVATAR_ACTUALIZADO', 'Foto de perfil cambiada', ip)
    return JSONResponse(content={'status': 'ok', 'avatar_url': avatar_url[:80] + '...'})


@router.post("/me/email/solicitar")
@limiter.limit("5/minute")
async def email_step1(request: Request, usuario: dict = Depends(get_current_user)):
    data     = await request.json() if await _has_body(request) else {}
    password = data.get('password', '').strip()
    nuevo    = data.get('nuevo_email', '').strip().lower()

    if not password or not nuevo:
        return format_error('password y nuevo_email son obligatorios.')

    if not validate_email(nuevo):
        return format_error('El formato de correo electrónico es inválido')

    user = _get_user(usuario['id'])
    if not user or not verify_password(password, user['password']):
        return JSONResponse(status_code=403, content={'error': 'Contraseña incorrecta.'})

    if user['email'].lower() == nuevo:
        return format_error('El nuevo email es igual al actual.')

    # Validación de unicidad
    conn = get_conn()
    try:
        duplicado = conn.execute(
            'SELECT id FROM usuarios WHERE LOWER(email) = ? AND id != ?',
            (nuevo, usuario['id'])
        ).fetchone()
        if duplicado:
            return JSONResponse(status_code=409, content={'error': 'El correo electrónico ya está registrado por otra cuenta.'})
    finally:
        conn.close()

    resultado = enviar_codigo_cambio_email(usuario['id'], nuevo, nuevo)
    if resultado.get('rate_limited'):
        return JSONResponse(
            status_code=429,
            content={'error': 'Espera antes de solicitar un nuevo código de verificación.'}
        )
    if resultado.get('enviado') or resultado.get('dev'):
        conn = get_conn()
        try:
            conn.execute('UPDATE usuarios SET email_pending = ? WHERE id = ?', (nuevo, usuario['id']))
            conn.commit()
        finally:
            conn.close()
    if resultado.get('enviado'):
        return JSONResponse(content={
            'status': 'ok',
            'mensaje': f'Código de verificación enviado al nuevo correo: {nuevo}.',
            'nuevo_email': nuevo
        })

    if resultado.get('dev'):
        return JSONResponse(content={
            'status': 'ok',
            'mensaje': f'Código de verificación generado para: {nuevo}.',
            'nuevo_email': nuevo,
            'dev_code': resultado.get('code'),
            'aviso': 'Modo desarrollo explícito activo (ARGOS_DEV_MODE). Código incluido para pruebas.',
        })

    return JSONResponse(
        status_code=503,
        content={'error': 'El servicio de correo no está disponible en este momento. Contacta al administrador.'}
    )


@router.post("/me/email/confirmar")
@limiter.limit("5/minute")
async def email_step2(request: Request, usuario: dict = Depends(get_current_user)):
    """
    Confirma el cambio de correo electrónico verificando el código.
    El correo final se toma EXCLUSIVAMENTE de la solicitud pendiente validada,
    impidiendo la sustitución arbitraria de la dirección.
    """
    data = await request.json() if await _has_body(request) else {}
    code = str(data.get('codigo', '')).strip()
    uid  = usuario['id']

    if not code:
        return format_error('El código de verificación es obligatorio.')

    ok, extra = validate_code('cambio_email', str(uid), code)
    if not ok:
        logger.warning(
            'Fallo de validación de cambio de correo user_id=%s motivo=%s ip=%s',
            uid,
            extra.get('reason', 'invalid'),
            request.client.host if request.client else 'unknown',
        )
        return JSONResponse(status_code=400, content={'error': 'Código incorrecto o expirado.'})

    nuevo_email = extra.get('nuevo_email', '').strip().lower()
    if not nuevo_email or not validate_email(nuevo_email):
        return JSONResponse(status_code=400, content={'error': 'Solicitud inválida o corrupta. Inicia el proceso nuevamente.'})

    conn = get_conn()
    try:
        # Re-verificar unicidad antes de persistir
        duplicado = conn.execute(
            'SELECT id FROM usuarios WHERE LOWER(email) = ? AND id != ?',
            (nuevo_email, uid)
        ).fetchone()
        if duplicado:
            conn.execute('UPDATE usuarios SET email_pending = NULL WHERE id = ?', (uid,))
            conn.commit()
            return JSONResponse(status_code=409, content={'error': 'El correo electrónico ya fue registrado por otra cuenta.'})

        conn.execute('UPDATE usuarios SET email = ?, email_pending = NULL WHERE id = ?', (nuevo_email, uid))
        conn.commit()
    finally:
        conn.close()

    ip = request.client.host if request.client else None
    registrar_auditoria(uid, 'EMAIL_ACTUALIZADO', f'Correo actualizado exitosamente a: {nuevo_email}', ip)
    return JSONResponse(content={
        'status': 'ok',
        'mensaje': 'Email actualizado correctamente.',
        'nuevo_email': nuevo_email
    })


@router.post("/me/email/finalizar")
async def email_step3(request: Request, usuario: dict = Depends(get_current_user)):
    """Alias de compatibilidad redirigido a confirmación segura."""
    return await email_step2(request, usuario)


@router.put("/me/password")
async def change_password_me(request: Request, usuario: dict = Depends(get_current_user)):
    data       = await request.json() if await _has_body(request) else {}
    actual     = data.get('actual', '').strip()
    nueva      = data.get('nueva', '').strip()
    confirmar  = data.get('confirmar', '').strip()
    uid        = usuario['id']

    if not actual or not nueva:
        return format_error('actual y nueva son obligatorios.')

    user = _get_user(uid)
    if not user or not verify_password(actual, user['password']):
        return JSONResponse(status_code=403, content={'error': 'Contraseña actual incorrecta.'})

    if nueva != confirmar:
        return format_error('La nueva contraseña y su confirmación no coinciden.')

    pass_ok, pass_msg = validate_password(nueva)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    conn = get_conn()
    conn.execute('UPDATE usuarios SET password=? WHERE id=?', (hash_password(nueva), uid))
    conn.commit()
    conn.close()
    revoke_all_user_sessions(uid)
    ip = request.client.host if request.client else None
    registrar_auditoria(uid, 'PASSWORD_CAMBIADA', 'Contraseña actualizada desde perfil', ip)
    return JSONResponse(content={'status': 'ok', 'mensaje': 'Contraseña actualizada correctamente. Inicia sesión con tu nueva contraseña.'})


@router.post("/me/2fa/activar")
def tfa_activar(usuario: dict = Depends(get_current_user)):
    avail = tf_check()
    if not avail['listo']:
        missing = [k for k, v in avail.items() if not v and k != 'listo']
        return JSONResponse(
            status_code=503,
            content={'error': f'2FA no disponible. Falta: {", ".join(missing)}. '
                              'Instala: pip install pyotp qrcode[pil] cryptography '
                              'y define ARGOS_FERNET_KEY en ENV.'}
        )

    uid  = usuario['id']
    user = _get_user(uid)
    if not user:
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})

    if user['fa2_activo']:
        return JSONResponse(status_code=400, content={'error': '2FA ya está activo. Desactívalo primero.'})

    secret         = generate_totp_secret()
    secret_cifrado = encrypt_secret(secret)
    qr_b64         = totp_qr_base64(secret, user['username'])

    conn = get_conn()
    conn.execute('UPDATE usuarios SET totp_secret=?, fa2_activo=0 WHERE id=?', (secret_cifrado, uid))
    conn.commit()
    conn.close()

    return JSONResponse(content={
        'status':   'ok',
        'qr_image': qr_b64,
        'mensaje':  'Escanea el QR con Google Authenticator u otra app TOTP y luego confirma con un código.',
    })


@router.post("/me/2fa/confirmar")
async def tfa_confirmar(request: Request, usuario: dict = Depends(get_current_user)):
    data  = await request.json() if await _has_body(request) else {}
    code  = str(data.get('codigo', '')).strip()
    uid   = usuario['id']
    user  = _get_user(uid)

    if not user or not user['totp_secret']:
        return JSONResponse(status_code=400, content={'error': 'No has iniciado el proceso de activación de 2FA.'})
    if user['fa2_activo']:
        return JSONResponse(status_code=400, content={'error': '2FA ya está activo.'})

    try:
        secret = decrypt_secret(user['totp_secret'])
    except ValueError:
        return JSONResponse(status_code=500, content={'error': 'Error al descifrar el secret TOTP.'})

    if not verify_totp(secret, code):
        return JSONResponse(status_code=400, content={'error': 'Código incorrecto. Verifica que la hora de tu dispositivo sea correcta.'})

    plain_codes, hashed_codes = generate_backup_codes()

    conn = get_conn()
    conn.execute('UPDATE usuarios SET fa2_activo=1, backup_codes=? WHERE id=?',
                 (serialize_backup_codes(hashed_codes), uid))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(uid, '2FA_ACTIVADO', 'Autenticación de dos factores activada', ip)

    return JSONResponse(content={
        'status':       'ok',
        'mensaje':      '2FA activado correctamente.',
        'backup_codes': plain_codes,
        'aviso':        '⚠️ Guarda estos códigos en un lugar seguro. Solo se muestran una vez.',
    })


@router.post("/me/2fa/desactivar")
async def tfa_desactivar(request: Request, usuario: dict = Depends(get_current_user)):
    data     = await request.json() if await _has_body(request) else {}
    password = data.get('password', '').strip()
    code     = str(data.get('codigo', '')).strip()
    uid      = usuario['id']
    user     = _get_user(uid)

    if not user:
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})
    if not user['fa2_activo']:
        return format_error('2FA no está activo.')
    if not verify_password(password, user['password']):
        return JSONResponse(status_code=403, content={'error': 'Contraseña incorrecta.'})

    try:
        secret = decrypt_secret(user['totp_secret'])
    except ValueError:
        return JSONResponse(status_code=500, content={'error': 'Error interno de 2FA.'})

    if not verify_totp(secret, code):
        return JSONResponse(status_code=400, content={'error': 'Código TOTP incorrecto.'})

    conn = get_conn()
    conn.execute('UPDATE usuarios SET fa2_activo=0, totp_secret=NULL, backup_codes=NULL WHERE id=?', (uid,))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(uid, '2FA_DESACTIVADO', 'Autenticación de dos factores desactivada', ip)
    return JSONResponse(content={'status': 'ok', 'mensaje': '2FA desactivado correctamente.'})


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
