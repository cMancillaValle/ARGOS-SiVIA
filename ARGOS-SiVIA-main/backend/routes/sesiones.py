"""
routes/sesiones.py
───────────────────
GET  /api/sesiones/activas   → Usuarios conectados ahora + módulo actual
POST /api/sesiones/modulo    → El frontend reporta el módulo que el usuario está viendo
"""

from flask import Blueprint, request, jsonify
from services.auth_service import (
    requiere_auth, requiere_permiso,
    actualizar_modulo_sesion, listar_sesiones_activas,
)

sesiones_bp = Blueprint('sesiones', __name__)


# ── GET /api/sesiones/activas ─────────────────────────────
@sesiones_bp.route('/activas', methods=['GET'])
@requiere_auth
@requiere_permiso('auditoria:ver')
def sesiones_activas():
    """Lista de usuarios conectados en este momento y su módulo actual."""
    sesiones = listar_sesiones_activas()
    return jsonify({
        'total': len(sesiones),
        'sesiones': sesiones,
    })


# ── POST /api/sesiones/modulo ─────────────────────────────
@sesiones_bp.route('/modulo', methods=['POST'])
@requiere_auth
def reportar_modulo():
    """
    Body JSON: { "modulo": "camaras" }
    Actualiza el módulo activo de la sesión del usuario autenticado.
    """
    data   = request.get_json(silent=True) or {}
    modulo = data.get('modulo', '').strip()

    if not modulo:
        return jsonify({'error': 'El campo "modulo" es obligatorio.'}), 400

    token = request.headers.get('X-Token')
    ok    = actualizar_modulo_sesion(token, modulo)

    if not ok:
        return jsonify({'error': 'No se pudo actualizar la sesión.'}), 400

    return jsonify({'status': 'ok'})