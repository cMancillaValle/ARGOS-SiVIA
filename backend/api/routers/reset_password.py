"""
api/routers/reset_password.py
────────────────────────────────────
Flujo de restablecimiento de contraseña sin autenticación.

POST /api/auth/reset-password/solicitar  → username/email → envía código
POST /api/auth/reset-password/confirmar  → código + nueva contraseña
"""

import sqlite3
import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services.auth_service import hash_password, registrar_auditoria
from services.email_service import (
    store_code, validate_code,
    enviar_codigo_reset_password,
)
from utils.limiter import limiter
from utils.validators import validate_password, format_error

router = APIRouter()
DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db'
))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/solicitar")
@limiter.limit("5/minute")
async def solicitar_reset(request: Request):
    """
    Body: { "identificador": "username o email" }
    """
    data  = await request.json() if await _has_body(request) else {}
    ident = data.get('identificador', '').strip()
    if not ident:
        return JSONResponse(status_code=400, content={'error': 'Proporciona tu usuario o email.'})

    conn = get_conn()
    user = conn.execute(
        'SELECT * FROM usuarios WHERE (username=? OR email=?) AND activo=1',
        (ident, ident)
    ).fetchone()
    conn.close()

    if not user:
        return JSONResponse(content={
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
    return JSONResponse(content=respuesta)


@router.post("/confirmar")
@limiter.limit("5/minute")
async def confirmar_reset(request: Request):
    """
    Body: { "username": "...", "codigo": "123456", "nueva_password": "..." }
    """
    data     = await request.json() if await _has_body(request) else {}
    username = data.get('username', '').strip()
    code     = str(data.get('codigo', '')).strip()
    nueva    = data.get('nueva_password', '').strip()

    if not all([username, code, nueva]):
        return format_error('username, codigo y nueva_password son obligatorios.')

    pass_ok, pass_msg = validate_password(nueva)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    ok, _ = validate_code('reset_pass', username, code)
    if not ok:
        return JSONResponse(status_code=400, content={'error': 'Código incorrecto o expirado. Solicita un nuevo código.'})

    conn = get_conn()
    user = conn.execute('SELECT id FROM usuarios WHERE username=? AND activo=1', (username,)).fetchone()
    if not user:
        conn.close()
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})

    conn.execute('UPDATE usuarios SET password=? WHERE id=?',
                 (hash_password(nueva), user['id']))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(user['id'], 'PASSWORD_RESET', 'Contraseña restablecida via email', ip)
    return JSONResponse(content={'status': 'ok', 'mensaje': 'Contraseña restablecida. Ya puedes iniciar sesión.'})


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
