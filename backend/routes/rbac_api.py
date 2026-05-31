"""
routes/rbac_api.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  API REST para el sistema RBAC

Endpoints:
  GET  /api/rbac/permisos          → permisos del usuario actual
  GET  /api/rbac/modulos           → módulos accesibles para el usuario
  GET  /api/rbac/matriz            → matriz completa (solo admin)
  POST /api/rbac/verificar         → verifica un permiso puntual

El frontend puede consumir estos endpoints al iniciar sesión
y construir la UI de forma dinámica (mostrar/ocultar módulos,
botones y acciones según el rol real del usuario).
"""

from flask import Blueprint, request, jsonify
from services.auth_service import requiere_auth, requiere_rol
from services.rbac import (
    PERMISOS,
    PERMISOS_ROL,
    tiene_permiso,
    obtener_permisos,
    puede_acceder_modulo,
)

rbac_bp = Blueprint("rbac", __name__)

# Módulos reconocidos por el sistema (para el menú lateral)
MODULOS = [
    "dashboard",
    "camaras",
    "eventos",
    "estadisticas",
    "usuarios",
    "configuracion",
    "logs",
    "sistema",
    "auditoria",
    "chatbot",
]


# ── GET /api/rbac/permisos ─────────────────────────────────────

@rbac_bp.route("/permisos", methods=["GET"])
@requiere_auth
def mis_permisos():
    """
    Devuelve todos los permisos del usuario autenticado.

    Respuesta:
        {
            "rol": "operador",
            "permisos": ["camaras:ver", "eventos:revisar", ...]
        }

    Uso en frontend (JS):
        const { permisos } = await GET('/api/rbac/permisos');
        const puedeEliminar = permisos.includes('camaras:eliminar');
    """
    usuario  = request.usuario
    permisos = obtener_permisos(usuario)
    return jsonify({
        "rol":      usuario["rol"],
        "usuario":  usuario["username"],
        "permisos": permisos,
        "total":    len(permisos),
    })


# ── GET /api/rbac/modulos ──────────────────────────────────────

@rbac_bp.route("/modulos", methods=["GET"])
@requiere_auth
def modulos_accesibles():
    """
    Devuelve los módulos a los que el usuario tiene acceso.
    Útil para renderizar el menú lateral dinámicamente.

    Respuesta:
        {
            "modulos": ["dashboard", "camaras", "eventos", "chatbot"]
        }
    """
    usuario  = request.usuario
    accesibles = [m for m in MODULOS if puede_acceder_modulo(usuario, m)]
    return jsonify({
        "rol":     usuario["rol"],
        "modulos": accesibles,
    })


# ── POST /api/rbac/verificar ───────────────────────────────────

@rbac_bp.route("/verificar", methods=["POST"])
@requiere_auth
def verificar_permiso():
    """
    Verifica si el usuario tiene un permiso específico.

    Body:  { "permiso": "camaras:eliminar" }
    Body:  { "permisos": ["camaras:ver", "camaras:editar"] }  ← multi

    Respuesta:
        { "permiso": "camaras:eliminar", "autorizado": false }
        { "resultados": {"camaras:ver": true, "camaras:editar": false} }
    """
    data    = request.get_json(silent=True) or {}
    usuario = request.usuario

    # Multi-verificación
    if "permisos" in data:
        lista = data["permisos"]
        if not isinstance(lista, list):
            return jsonify({"error": '"permisos" debe ser un array.'}), 400
        resultados = {p: tiene_permiso(usuario, p) for p in lista}
        return jsonify({"rol": usuario["rol"], "resultados": resultados})

    # Verificación individual
    permiso = data.get("permiso", "").strip()
    if not permiso:
        return jsonify({"error": 'Se requiere "permiso" o "permisos".'}), 400

    return jsonify({
        "rol":        usuario["rol"],
        "permiso":    permiso,
        "autorizado": tiene_permiso(usuario, permiso),
    })


# ── GET /api/rbac/matriz ───────────────────────────────────────

@rbac_bp.route("/matriz", methods=["GET"])
@requiere_rol("admin")
def matriz_completa():
    """
    Devuelve la matriz RBAC completa (solo admin).
    Útil para auditoría y documentación interna.

    Respuesta:
        {
            "permisos_disponibles": {...},
            "matriz": {
                "admin":      ["camaras:ver", ...],
                "supervisor": [...],
                ...
            }
        }
    """
    matriz = {
        rol: sorted(permisos)
        for rol, permisos in PERMISOS_ROL.items()
    }
    return jsonify({
        "permisos_disponibles": PERMISOS,
        "total_permisos":       len(PERMISOS),
        "roles":                list(PERMISOS_ROL.keys()),
        "matriz":               matriz,
    })
