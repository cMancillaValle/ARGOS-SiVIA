"""
services/rbac.py  (sin imports Flask — compatible FastAPI y Python puro)
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Control de Acceso Basado en Roles (RBAC)

Las funciones de validación son Python puro.
Los decoradores Flask han sido removidos — usar las dependencias
de auth_service.py (require_permission, require_any_permission, require_role)
en su lugar dentro de FastAPI.
"""

from functools import wraps

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
    "admin": set(PERMISOS.keys()),

    # ── SUPERVISOR ────────────────────────────────────────────
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
#  FUNCIONES PURAS DE VALIDACIÓN
# ══════════════════════════════════════════════════════════════

def tiene_permiso(usuario: dict, permiso: str) -> bool:
    """
    Verifica si un usuario tiene un permiso específico.
    100% Python puro, sin dependencias de framework.
    """
    if not usuario or not permiso:
        return False
    rol = usuario.get("rol", "")
    if rol == "admin":
        return True
    permisos_del_rol = PERMISOS_ROL.get(rol, set())
    return permiso in permisos_del_rol


def obtener_permisos(usuario: dict) -> list[str]:
    """Devuelve la lista completa de permisos del usuario."""
    rol = usuario.get("rol", "")
    return sorted(PERMISOS_ROL.get(rol, set()))


def puede_acceder_modulo(usuario: dict, modulo: str) -> bool:
    """Verifica si el usuario tiene al menos UN permiso en el módulo dado."""
    rol = usuario.get("rol", "")
    permisos = PERMISOS_ROL.get(rol, set())
    return any(p.startswith(f"{modulo}:") for p in permisos)


# ══════════════════════════════════════════════════════════════
#  DECORADORES (STUBS — solo para compatibilidad durante la migración)
#  Los routers FastAPI deben usar Depends(require_permission("modulo:accion"))
#  definidas en services/auth_service.py
# ══════════════════════════════════════════════════════════════

def requiere_permiso(permiso: str):
    """
    STUB para compatibilidad. En FastAPI usar:
        from services.auth_service import require_permission
        usuario = Depends(require_permission("modulo:accion"))
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            raise RuntimeError(
                f"requiere_permiso('{permiso}') Flask stub invocado en contexto FastAPI. "
                "Usa Depends(require_permission(...)) en su lugar."
            )
        return decorated
    return decorator


def requiere_cualquier_permiso(*permisos: str):
    """STUB para compatibilidad — usar require_any_permission() de auth_service."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            raise RuntimeError("requiere_cualquier_permiso Flask stub invocado en FastAPI.")
        return decorated
    return decorator
