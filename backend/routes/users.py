"""
routes/users.py
───────────────
GET    /api/usuarios          → Lista usuarios (usuarios:ver)
POST   /api/usuarios          → Crear usuario (usuarios:crear)
GET    /api/usuarios/<id>     → Detalle usuario (usuarios:ver_detalle)
PUT    /api/usuarios/<id>     → Editar usuario (usuarios:editar)
DELETE /api/usuarios/<id>     → Desactivar usuario (usuarios:desactivar)
PUT    /api/usuarios/<id>/password → Cambiar contraseña (propio o usuarios:cambiar_password)

FIX v1.2.1: Migrado de @requiere_rol('admin') a @requiere_permiso(...)
            El rol 'auditor' puede ver usuarios pero no crearlos/editarlos.
"""

import sqlite3
import os
from flask import Blueprint, request, jsonify
from services.auth_service import (
    hash_password, requiere_auth, registrar_auditoria,
    requiere_permiso,
)
from utils.validators import validate_email, validate_password, format_error

users_bp = Blueprint('users', __name__)
DB_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db'))
ROLES_VALIDOS = ('admin', 'supervisor', 'operador', 'analista', 'tecnico', 'auditor')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── GET /api/usuarios ─────────────────────────────────
@users_bp.route('', methods=['GET'])
@requiere_auth
@requiere_permiso('usuarios:ver')
def list_users():
    conn = get_conn()
    rows = conn.execute(
        'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios ORDER BY nombre'
    ).fetchall()
    conn.close()
    return jsonify({'total': len(rows), 'usuarios': [dict(r) for r in rows]})


# ── GET /api/usuarios/<id> ────────────────────────────
@users_bp.route('/<int:user_id>', methods=['GET'])
@requiere_auth
@requiere_permiso('usuarios:ver_detalle')
def get_user(user_id):
    conn = get_conn()
    user = conn.execute(
        'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios WHERE id=?',
        (user_id,)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Usuario no encontrado.'}), 404
    return jsonify(dict(user))


# ── POST /api/usuarios ────────────────────────────────
@users_bp.route('', methods=['POST'])
@requiere_auth
@requiere_permiso('usuarios:crear')
def create_user():
    data = request.get_json(silent=True) or {}
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
            'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios WHERE id=?',
            (uid,)
        ).fetchone()
        conn.close()
        registrar_auditoria(request.usuario['id'], 'USUARIO_CREADO', f'Usuario {data["username"]} creado')
        return jsonify(dict(user)), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f'El username "{data["username"]}" ya existe.'}), 409


# ── PUT /api/usuarios/<id> ────────────────────────────
@users_bp.route('/<int:user_id>', methods=['PUT'])
@requiere_auth
@requiere_permiso('usuarios:editar')
def update_user(user_id):
    data   = request.get_json(silent=True) or {}
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
        return jsonify({'error': 'No hay campos para actualizar.'}), 400

    params.append(user_id)
    conn = get_conn()
    conn.execute(f'UPDATE usuarios SET {", ".join(sets)} WHERE id=?', params)
    conn.commit()
    user = conn.execute(
        'SELECT id, username, nombre, email, rol, activo, creado_en FROM usuarios WHERE id=?',
        (user_id,)
    ).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Usuario no encontrado.'}), 404
    registrar_auditoria(request.usuario['id'], 'USUARIO_ACTUALIZADO', f'Usuario ID {user_id}')
    return jsonify(dict(user))


# ── DELETE (desactivar) /api/usuarios/<id> ────────────
@users_bp.route('/<int:user_id>', methods=['DELETE'])
@requiere_auth
@requiere_permiso('usuarios:desactivar')
def deactivate_user(user_id):
    if user_id == request.usuario['id']:
        return jsonify({'error': 'No puedes desactivar tu propia cuenta.'}), 400
    conn = get_conn()
    user = conn.execute('SELECT username FROM usuarios WHERE id=?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'Usuario no encontrado.'}), 404
    conn.execute('UPDATE usuarios SET activo=0 WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    registrar_auditoria(request.usuario['id'], 'USUARIO_DESACTIVADO', f'Usuario {user["username"]}')
    return jsonify({'status': 'ok', 'mensaje': f'Usuario {user["username"]} desactivado.'})


# ── PUT /api/usuarios/<id>/password ──────────────────
@users_bp.route('/<int:user_id>/password', methods=['PUT'])
@requiere_auth
def change_password(user_id):
    # Propio usuario O alguien con permiso explícito de cambiar passwords
    from services.auth_service import tiene_permiso
    es_propio = request.usuario['id'] == user_id
    es_admin  = tiene_permiso(request.usuario, 'usuarios:cambiar_password')
    if not es_propio and not es_admin:
        return jsonify({'error': 'No tienes permiso para cambiar esta contraseña.'}), 403

    data  = request.get_json(silent=True) or {}
    nueva = data.get('nueva_password', '').strip()
    
    pass_ok, pass_msg = validate_password(nueva)
    if not pass_ok:
        return format_error(f'La contraseña es débil: {pass_msg}')

    conn = get_conn()
    conn.execute('UPDATE usuarios SET password=? WHERE id=?', (hash_password(nueva), user_id))
    conn.commit()
    conn.close()
    registrar_auditoria(request.usuario['id'], 'PASSWORD_CAMBIADA', f'Usuario ID {user_id}')
    return jsonify({'status': 'ok', 'mensaje': 'Contraseña actualizada.'})
