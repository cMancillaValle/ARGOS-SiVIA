"""
services/rbac.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Control de Acceso Basado en Roles (RBAC)
────────────────────────────────────────────────────────────

Uso:
    from services.rbac import tiene_permiso, requiere_permiso, PERMISOS_ROL

Roles disponibles:
    admin, supervisor, operador, analista, tecnico, auditor
"""

from functools import wraps
from flask import request, jsonify

# ══════════════════════════════════════════════════════════════
#  CATÁLOGO DE PERMISOS
#  Formato: "módulo:acción"
# ══════════════════════════════════════════════════════════════

PERMISOS = {
    # ── Dashboard ─────────────────────────────────────────────
    "dashboard:ver":           "Ver panel principal",
    "dashboard:exportar":      "Exportar datos del dashboard",

    # ── Cámaras ───────────────────────────────────────────────
    "camaras:ver":             "Ver lista de cámaras",
    "camaras:ver_detalle":     "Ver detalle de una cámara",
    "camaras:crear":           "Registrar nueva cámara",
    "camaras:editar":          "Modificar datos de cámara",
    "camaras:eliminar":        "Eliminar cámara del sistema",
    "camaras:ver_asignadas":   "Ver solo cámaras asignadas al operador",

    # ── Eventos ───────────────────────────────────────────────
    "eventos:ver":             "Ver lista de eventos",
    "eventos:ver_detalle":     "Ver detalle de evento",
    "eventos:crear":           "Registrar evento (sistema IA)",
    "eventos:revisar":         "Confirmar o descartar evento",
    "eventos:exportar":        "Exportar eventos a CSV",

    # ── Estadísticas ──────────────────────────────────────────
    "estadisticas:ver":        "Ver estadísticas generales",
    "estadisticas:ver_hoy":    "Ver actividad del día",
    "estadisticas:historico":  "Ver datos históricos",
    "estadisticas:exportar":   "Exportar reportes",

    # ── Usuarios ──────────────────────────────────────────────
    "usuarios:ver":            "Ver lista de usuarios",
    "usuarios:ver_detalle":    "Ver detalle de usuario",
    "usuarios:crear":          "Crear nuevo usuario",
    "usuarios:editar":         "Editar datos de usuario",
    "usuarios:desactivar":     "Desactivar usuario",
    "usuarios:cambiar_password": "Cambiar contraseña de cualquier usuario",

    # ── Configuración ─────────────────────────────────────────
    "configuracion:ver":       "Ver configuración del sistema",
    "configuracion:editar":    "Modificar configuración",
    "configuracion:ia":        "Configurar parámetros del modelo IA",

    # ── Logs ──────────────────────────────────────────────────
    "logs:ver":                "Ver logs del sistema",
    "logs:ver_tecnicos":       "Ver logs técnicos detallados",
    "logs:exportar":           "Exportar logs",

    # ── Sistema / Infraestructura ──────────────────────────────
    "sistema:ver_estado":      "Ver estado general del sistema",
    "sistema:reiniciar":       "Reiniciar servicios",
    "sistema:mantenimiento":   "Gestionar mantenimiento de cámaras",
    "sistema:ver_metricas":    "Ver métricas de rendimiento",

    # ── Auditoría ─────────────────────────────────────────────
    "auditoria:ver":           "Ver log de auditoría",
    "auditoria:exportar":      "Exportar log de auditoría",
    "auditoria:ver_stats":     "Ver estadísticas de auditoría",

    # ── Chatbot Hermes ────────────────────────────────────────
    "chatbot:usar":            "Usar Hermes IA",
    "chatbot:consulta_admin":  "Consultas administrativas en Hermes",
    "chatbot:consulta_tecnica":"Consultas técnicas en Hermes",
    "chatbot:consulta_datos":  "Consultas de datos/estadísticas en Hermes",
}


# ══════════════════════════════════════════════════════════════
#  MATRIZ RBAC  -  rol → conjunto de permisos
# ══════════════════════════════════════════════════════════════

PERMISOS_ROL: dict[str, set[str]] = {

    # ── ADMIN ─────────────────────────────────────────────────
    # Acceso total sin restricción
    "admin": set(PERMISOS.keys()),

    # ── SUPERVISOR ────────────────────────────────────────────
    # Monitoreo completo, eventos, estadísticas; sin gestión de infraestructura
    "supervisor": {
        "dashboard:ver",
        "dashboard:exportar",
        "camaras:ver",
        "camaras:ver_detalle",
        "eventos:ver",
        "eventos:ver_detalle",
        "eventos:revisar",
        "eventos:exportar",
        "estadisticas:ver",
        "estadisticas:ver_hoy",
        "estadisticas:historico",
        "estadisticas:exportar",
        "logs:ver",
        "sistema:ver_estado",
        "sistema:ver_metricas",
        "auditoria:ver",
        "auditoria:ver_stats",
        "chatbot:usar",
        "chatbot:consulta_datos",
    },

    # ── OPERADOR ──────────────────────────────────────────────
    # Cámaras asignadas, alertas en tiempo real, marcar eventos
    "operador": {
        "dashboard:ver",
        "camaras:ver",
        "camaras:ver_detalle",
        "camaras:ver_asignadas",
        "eventos:ver",
        "eventos:ver_detalle",
        "eventos:revisar",
        "estadisticas:ver_hoy",
        "sistema:ver_estado",
        "chatbot:usar",
    },

    # ── ANALISTA ──────────────────────────────────────────────
    # Estadísticas, datos históricos; solo lectura operacional
    "analista": {
        "dashboard:ver",
        "camaras:ver",
        "eventos:ver",
        "eventos:ver_detalle",
        "eventos:exportar",
        "estadisticas:ver",
        "estadisticas:ver_hoy",
        "estadisticas:historico",
        "estadisticas:exportar",
        "chatbot:usar",
        "chatbot:consulta_datos",
    },

    # ── TECNICO ───────────────────────────────────────────────
    # Cámaras, sistema, infraestructura y logs técnicos
    "tecnico": {
        "dashboard:ver",
        "camaras:ver",
        "camaras:ver_detalle",
        "camaras:crear",
        "camaras:editar",
        "configuracion:ver",
        "configuracion:ia",
        "logs:ver",
        "logs:ver_tecnicos",
        "logs:exportar",
        "sistema:ver_estado",
        "sistema:reiniciar",
        "sistema:mantenimiento",
        "sistema:ver_metricas",
        "chatbot:usar",
        "chatbot:consulta_tecnica",
    },

    # ── AUDITOR ───────────────────────────────────────────────
    # Solo lectura: auditoría del sistema, logs, historial de eventos
    # NO accede a estadísticas (eso es rol de analista)
    "auditor": {
        "dashboard:ver",
        "camaras:ver",
        "eventos:ver",
        "eventos:ver_detalle",
        "eventos:exportar",
        "logs:ver",
        "auditoria:ver",
        "auditoria:exportar",
        "auditoria:ver_stats",
        "chatbot:usar",
    },
}


# ══════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL: tiene_permiso
# ══════════════════════════════════════════════════════════════

def tiene_permiso(usuario: dict, permiso: str) -> bool:
    """
    Verifica si un usuario tiene un permiso específico.

    Args:
        usuario:  dict con al menos la clave 'rol'
                  Ej: {'id': 1, 'username': 'admin', 'rol': 'admin'}
        permiso:  string con formato 'módulo:acción'
                  Ej: 'camaras:eliminar', 'chatbot:consulta_tecnica'

    Returns:
        True  → el rol del usuario incluye ese permiso
        False → acceso denegado

    Ejemplos:
        tiene_permiso({'rol': 'operador'}, 'eventos:revisar')  → True
        tiene_permiso({'rol': 'auditor'},  'usuarios:crear')   → False
        tiene_permiso({'rol': 'admin'},    'cualquier:cosa')   → True
    """
    if not usuario or not permiso:
        return False

    rol = usuario.get("rol", "")

    # Admin siempre tiene acceso total
    if rol == "admin":
        return True

    permisos_del_rol = PERMISOS_ROL.get(rol, set())
    return permiso in permisos_del_rol


def obtener_permisos(usuario: dict) -> list[str]:
    """
    Devuelve la lista completa de permisos del usuario.

    Útil para enviar al frontend y construir la UI dinámica.
    """
    rol = usuario.get("rol", "")
    return sorted(PERMISOS_ROL.get(rol, set()))


def puede_acceder_modulo(usuario: dict, modulo: str) -> bool:
    """
    Verifica si el usuario tiene al menos UN permiso en el módulo dado.

    Args:
        modulo: nombre del módulo (ej: 'camaras', 'estadisticas')

    Uso típico: controlar visibilidad de secciones en el menú.
    """
    rol = usuario.get("rol", "")
    permisos = PERMISOS_ROL.get(rol, set())
    return any(p.startswith(f"{modulo}:") for p in permisos)


# ══════════════════════════════════════════════════════════════
#  DECORADORES FLASK
# ══════════════════════════════════════════════════════════════

def requiere_permiso(permiso: str):
    """
    Decorador que valida un permiso específico en el endpoint.

    Requiere que @requiere_auth haya sido aplicado antes,
    o que request.usuario esté disponible.

    Uso:
        @app.route('/api/camaras', methods=['DELETE'])
        @requiere_auth
        @requiere_permiso('camaras:eliminar')
        def eliminar_camara():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            usuario = getattr(request, "usuario", None)
            if not usuario:
                return jsonify({"error": "No autorizado."}), 401
            if not tiene_permiso(usuario, permiso):
                return jsonify({
                    "error": f"Acceso denegado.",
                    "detalle": f"Tu rol '{usuario.get('rol')}' no tiene el permiso '{permiso}'.",
                    "permiso_requerido": permiso,
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def requiere_cualquier_permiso(*permisos: str):
    """
    Decorador que pasa si el usuario tiene AL MENOS UNO de los permisos dados.

    Uso:
        @requiere_cualquier_permiso('camaras:editar', 'camaras:crear')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            usuario = getattr(request, "usuario", None)
            if not usuario:
                return jsonify({"error": "No autorizado."}), 401
            if not any(tiene_permiso(usuario, p) for p in permisos):
                return jsonify({
                    "error": "Acceso denegado.",
                    "detalle": f"Se requiere uno de: {', '.join(permisos)}",
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
