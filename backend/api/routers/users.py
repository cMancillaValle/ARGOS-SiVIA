"""
api/routers/users.py
────────────────────────────────────
GET    /api/usuarios          → Lista usuarios
POST   /api/usuarios          → Crear usuario
GET    /api/usuarios/<id>     → Detalle
PUT    /api/usuarios/<id>     → Editar
DELETE /api/usuarios/<id>     → Desactivar
PUT    /api/usuarios/<id>/password → Cambiar contraseña
"""

import sqlite3
import os
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from services.auth_service import (
    hash_password, registrar_auditoria, get_current_user,
    require_permission, tiene_permiso,
)
from utils.validators import validate_email, validate_password, format_error

router = APIRouter()

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db'
))
ROLES_VALIDOS = ('admin', 'supervisor', 'operador', 'analista', 'tecnico', 'auditor')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("")
def list_users(usuario: dict = Depends(require_permission("usuarios:ver"))):
    conn = get_conn()
    rows = conn.execute(
        'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios ORDER BY nombre'
    ).fetchall()
    conn.close()
    return JSONResponse(content={'total': len(rows), 'usuarios': [dict(r) for r in rows]})


@router.get("/{user_id}")
def get_user(user_id: int, usuario: dict = Depends(require_permission("usuarios:ver_detalle"))):
    conn = get_conn()
    user = conn.execute(
        'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios WHERE id=?', (user_id,)
    ).fetchone()
    conn.close()
    if not user:
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})
    return JSONResponse(content=dict(user))


@router.post("")
async def create_user(request: Request, usuario: dict = Depends(require_permission("usuarios:crear"))):
    data = await request.json()
    for campo in ['username', 'password', 'nombre', 'email', 'rol']:
        if not data.get(campo):
            return format_error(f'El campo "{campo}" es obligatorio.')

    if data['rol'] not in ROLES_VALIDOS:
        return format_error(f'Rol inválido. Válidos: {", ".join(ROLES_VALIDOS)}')
    if not validate_email(data['email']):
        return format_error('El formato de correo electrónico es inválido')
    pass_ok, pass_msg = validate_password(data['password'])
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    conn = get_conn()
    try:
        cursor = conn.execute(
            'INSERT INTO usuarios (username, password, nombre, email, rol) VALUES (?,?,?,?,?)',
            (data['username'], hash_password(data['password']), data['nombre'], data['email'], data['rol'])
        )
        conn.commit()
        uid  = cursor.lastrowid
        user = conn.execute(
            'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios WHERE id=?', (uid,)
        ).fetchone()
        conn.close()
        ip = request.client.host if request.client else None
        registrar_auditoria(usuario['id'], 'USUARIO_CREADO', f'Usuario {data["username"]} creado', ip)
        return JSONResponse(status_code=201, content=dict(user))
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse(status_code=409, content={'error': f'El username "{data["username"]}" ya existe.'})


@router.put("/{user_id}")
async def update_user(user_id: int, request: Request,
                      usuario: dict = Depends(require_permission("usuarios:editar"))):
    data   = await request.json()
    campos = ['nombre', 'email', 'rol', 'activo']
    sets, params = [], []

    for campo in campos:
        if campo in data:
            if campo == 'rol' and data[campo] not in ROLES_VALIDOS:
                return format_error('Rol inválido.')
            if campo == 'email' and not validate_email(data[campo]):
                return format_error('El formato de correo electrónico es inválido.')
            sets.append(f'{campo} = ?')
            params.append(data[campo])

    if not sets:
        return JSONResponse(status_code=400, content={'error': 'No hay campos para actualizar.'})

    params.append(user_id)
    conn = get_conn()
    conn.execute(f'UPDATE usuarios SET {", ".join(sets)} WHERE id=?', params)
    conn.commit()
    user = conn.execute(
        'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios WHERE id=?', (user_id,)
    ).fetchone()
    conn.close()
    if not user:
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'USUARIO_ACTUALIZADO', f'Usuario ID {user_id}', ip)
    return JSONResponse(content=dict(user))


@router.delete("/{user_id}")
async def deactivate_user(user_id: int, request: Request,
                          usuario: dict = Depends(require_permission("usuarios:desactivar"))):
    if user_id == usuario['id']:
        return JSONResponse(status_code=400, content={'error': 'No puedes desactivar tu propia cuenta.'})
    conn = get_conn()
    user = conn.execute('SELECT username FROM usuarios WHERE id=?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return JSONResponse(status_code=404, content={'error': 'Usuario no encontrado.'})
    conn.execute('UPDATE usuarios SET activo=0 WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'USUARIO_DESACTIVADO', f'Usuario {user["username"]}', ip)
    return JSONResponse(content={'status': 'ok', 'mensaje': f'Usuario {user["username"]} desactivado.'})


@router.put("/{user_id}/password")
async def change_password(user_id: int, request: Request,
                          usuario: dict = Depends(get_current_user)):
    es_propio = usuario['id'] == user_id
    es_admin  = tiene_permiso(usuario, 'usuarios:cambiar_password')
    if not es_propio and not es_admin:
        return JSONResponse(status_code=403, content={'error': 'No tienes permiso para cambiar esta contraseña.'})

    data  = await request.json()
    nueva = data.get('nueva_password', '').strip()
    pass_ok, pass_msg = validate_password(nueva)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    conn = get_conn()
    conn.execute('UPDATE usuarios SET password=? WHERE id=?', (hash_password(nueva), user_id))
    conn.commit()
    conn.close()
    ip = request.client.host if request.client else None
    registrar_auditoria(usuario['id'], 'PASSWORD_CAMBIADA', f'Usuario ID {user_id}', ip)
    return JSONResponse(content={'status': 'ok', 'mensaje': 'Contraseña actualizada.'})
