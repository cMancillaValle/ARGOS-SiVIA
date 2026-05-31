"""
services/hermes_service.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Hermes IA - Orquestador Principal

Reemplaza la lógica monolítica de routes/chat.py.
La ruta solo valida el body y delega aquí todo el procesamiento.

Flujo:
  1. Cleanup de sesiones expiradas
  2. Recuperar historial de sesión (RAM)
  3. Motor NLP → detectar intención + entidades
  4. Motor de salud → SystemHealthSnapshot
  5. Verificar RBAC por intent detectado
  6. Construir respuesta de BD según intent
  7. Armar acciones y sugerencias por rol
  8. Guardar turno en sesión
  9. Retornar HermesResponse tipado
"""

from __future__ import annotations
import os
import sqlite3
import html
import logging
from datetime import datetime
from typing import Optional

from services.hermes_context import (
    HermesRequest, HermesResponse,
    AlertaSummary, AccionSugerida, SystemHealthSnapshot,
)
from services.hermes_intents import detectar_intencion
from services.system_health  import obtener_snapshot
from services.hermes_session import session_cache
from services.rbac           import tiene_permiso

log = logging.getLogger("ARGOS.HermesService")

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "database", "argos.db"
))


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _num(val: int) -> str:
    return f"{val:,}".replace(",", ".")


def _sanitize(text: str) -> str:
    """Escapa HTML para evitar XSS en el contenido de respuesta."""
    return html.escape(text, quote=False)


# ══════════════════════════════════════════════════════════════
#  MAP: intent → permiso requerido
# ══════════════════════════════════════════════════════════════

INTENT_PERMISSION_MAP: dict[str, str] = {
    "estado_sistema": "sistema:ver_estado",
    "camaras":        "camaras:ver",
    "alertas":        "eventos:ver",
    "estadisticas":   "estadisticas:ver",
    "historico":      "estadisticas:historico",
    "logs":           "logs:ver_tecnicos",
    "usuarios":       "usuarios:ver",
    "auditoria":      "auditoria:ver",
    # 'rol', 'ayuda' y 'desconocido' no requieren permiso extra
}


# ══════════════════════════════════════════════════════════════
#  ACCIONES POR ROL
# ══════════════════════════════════════════════════════════════

def _acciones_por_rol(rol: str, intent: str) -> list[AccionSugerida]:
    """Devuelve botones de acción rápida contextual según rol e intent."""
    acciones: list[AccionSugerida] = []

    if intent == "alertas":
        if rol in ("admin", "supervisor", "operador"):
            acciones.append(AccionSugerida(
                id="revisar_alertas",
                label="📋 Revisar alertas pendientes",
                endpoint="/api/eventos?estado=pendiente",
                metodo="GET",
                permiso_requerido="eventos:ver",
            ))
        if rol in ("admin", "supervisor", "operador", "analista", "auditor"):
            acciones.append(AccionSugerida(
                id="exportar_eventos",
                label="📤 Exportar eventos",
                endpoint="/api/eventos/exportar",
                metodo="GET",
                permiso_requerido="eventos:exportar",
            ))

    elif intent == "camaras":
        acciones.append(AccionSugerida(
            id="ver_camaras",
            label="📷 Ver lista de cámaras",
            endpoint="/api/camaras",
            metodo="GET",
            permiso_requerido="camaras:ver",
        ))
        if rol in ("admin", "tecnico"):
            acciones.append(AccionSugerida(
                id="crear_camara",
                label="➕ Registrar nueva cámara",
                endpoint="/api/camaras",
                metodo="POST",
                permiso_requerido="camaras:crear",
            ))

    elif intent == "estadisticas":
        if rol in ("admin", "supervisor", "analista"):
            acciones.append(AccionSugerida(
                id="exportar_stats",
                label="📊 Exportar reporte",
                endpoint="/api/stats/exportar",
                metodo="GET",
                permiso_requerido="estadisticas:exportar",
            ))

    elif intent == "logs":
        if rol in ("admin", "tecnico"):
            acciones.append(AccionSugerida(
                id="ver_logs_tecnicos",
                label="🔧 Ver logs técnicos completos",
                endpoint="/api/auditoria",
                metodo="GET",
                permiso_requerido="logs:ver_tecnicos",
            ))

    elif intent == "usuarios":
        if rol == "admin":
            acciones.append(AccionSugerida(
                id="crear_usuario",
                label="👤 Crear nuevo usuario",
                endpoint="/api/usuarios",
                metodo="POST",
                permiso_requerido="usuarios:crear",
            ))

    return acciones


# ══════════════════════════════════════════════════════════════
#  SUGERENCIAS CONTEXTUALES
# ══════════════════════════════════════════════════════════════

SUGERENCIAS_POR_INTENT: dict[str, list[str]] = {
    "estado_sistema": [
        "¿Cuántas cámaras están offline?",
        "¿Cuántas alertas hay pendientes?",
        "Muéstrame las estadísticas del sistema",
    ],
    "camaras": [
        "¿Cuáles cámaras están fuera de línea?",
        "¿Cuántas cámaras hay en total?",
        "Muéstrame el estado del sistema",
    ],
    "alertas": [
        "¿Cuántas alertas hay hoy?",
        "Muéstrame el historial de eventos",
        "¿Cuál es el estado general del sistema?",
    ],
    "estadisticas": [
        "¿Cuál es la precisión del modelo IA?",
        "Muéstrame los datos históricos",
        "¿Cuántas alertas se confirmaron?",
    ],
    "historico": [
        "¿Cuáles son las estaciones con más eventos?",
        "¿Cuántos eventos hubo este mes?",
        "Muéstrame las estadísticas actuales",
    ],
    "logs": [
        "¿Quién realizó la última acción técnica?",
        "Muéstrame el registro de auditoría",
        "¿Cuál es el estado del sistema?",
    ],
    "usuarios": [
        "¿Cuántos usuarios hay activos?",
        "¿Cuál es mi rol y permisos?",
        "Muéstrame el log de auditoría",
    ],
    "auditoria": [
        "¿Quién fue el último en iniciar sesión?",
        "Muéstrame los logs técnicos",
        "¿Cuántos usuarios hay en el sistema?",
    ],
    "rol": [
        "¿Qué puedo hacer con mi rol?",
        "Muéstrame el estado del sistema",
        "¿Cuántas alertas hay pendientes?",
    ],
    "ayuda": [
        "¿Cuántas cámaras están activas?",
        "¿Cuántas alertas hay hoy?",
        "¿Cuál es el estado del sistema?",
    ],
    "saludo": [
        "¿Cuáles son tus funciones?",
        "¿Cuál es el estado del sistema?",
        "¿Cuántas alertas hay pendientes?",
    ],
    "desconocido": [
        "¿Cuál es el estado del sistema?",
        "¿Cuántas alertas hay pendientes?",
        "¿Cuántas cámaras están activas?",
    ],
}


# ══════════════════════════════════════════════════════════════
#  GENERADORES DE CONTENIDO (consultas BD)
# ══════════════════════════════════════════════════════════════

def _contenido_estado_sistema(snapshot: SystemHealthSnapshot) -> tuple[str, list[AlertaSummary]]:
    icono_nivel = {"normal": "✅", "warning": "⚠️", "critical": "🔴"}.get(snapshot.nivel, "⚠️")
    texto = (
        f"📡 **Estado del sistema ARGOS:**\n"
        f"• Estado: {icono_nivel} {snapshot.nivel.upper()}\n"
        f"• Cámaras activas: {snapshot.camaras_activas} de {snapshot.camaras_total}\n"
        f"• Cámaras offline: {snapshot.camaras_offline}\n"
        f"• Alertas pendientes: {snapshot.alertas_pendientes}\n"
        f"• Modelo IA: YOLOv8 · {snapshot.fps_estimado} FPS\n"
        f"• Uptime: {snapshot.uptime_pct}%\n"
        f"• Verificación: {snapshot.evaluado_en}"
    )
    return texto, []


def _contenido_camaras() -> tuple[str, list[AlertaSummary]]:
    conn = _conn()
    rows    = conn.execute("SELECT estado, COUNT(*) as total FROM camaras GROUP BY estado").fetchall()
    resumen = {r["estado"]: r["total"] for r in rows}
    total   = sum(resumen.values())
    fuera   = conn.execute(
        "SELECT codigo, estacion FROM camaras WHERE estado != 'activa' ORDER BY estado"
    ).fetchall()
    conn.close()

    texto = (
        f"📷 **Cámaras del sistema:**\n"
        f"• Total instaladas: {total}\n"
        f"• Activas: {resumen.get('activa', 0)}\n"
        f"• Offline: {resumen.get('offline', 0)}\n"
        f"• En mantenimiento: {resumen.get('mantenimiento', 0)}\n"
    )
    if fuera:
        texto += "\n⚠️ Cámaras fuera de línea:\n"
        for c in fuera[:5]:
            texto += f"  · {_sanitize(c['codigo'])} - {_sanitize(c['estacion'])}\n"
    return texto.strip(), []


def _contenido_alertas() -> tuple[str, list[AlertaSummary]]:
    hoy   = datetime.now().strftime("%Y-%m-%d")
    conn  = _conn()
    total = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    pend  = conn.execute("SELECT COUNT(*) FROM eventos WHERE estado='pendiente'").fetchone()[0]
    hoy_c = conn.execute(
        "SELECT COUNT(*) FROM eventos WHERE detectado_en LIKE ?", (f"{hoy}%",)
    ).fetchone()[0]
    ultimos = conn.execute(
        """SELECT e.tipo, e.confianza, e.detectado_en, c.codigo, c.estacion
           FROM eventos e JOIN camaras c ON c.id = e.camara_id
           WHERE e.estado = 'pendiente'
           ORDER BY e.detectado_en DESC LIMIT 5"""
    ).fetchall()
    conn.close()

    texto = (
        f"🔔 **Alertas del sistema:**\n"
        f"• Total registradas: {_num(total)}\n"
        f"• Pendientes de revisión: {pend}\n"
        f"• Detectadas hoy: {hoy_c}\n"
    )

    alertas_summary: list[AlertaSummary] = []
    if ultimos:
        texto += "\n🔴 Últimas alertas pendientes:\n"
        for u in ultimos:
            hora = u["detectado_en"][11:16] if u["detectado_en"] else "--:--"
            confianza = int((u["confianza"] or 0) * 100)
            texto += f"  · [{hora}] {u['codigo']} - {u['estacion']} ({confianza}%)\n"
            alertas_summary.append(AlertaSummary(
                camara_codigo=u["codigo"],
                estacion=u["estacion"],
                tipo=u["tipo"],
                hora=hora,
                confianza_pct=confianza,
            ))
    return texto.strip(), alertas_summary


def _contenido_estadisticas() -> tuple[str, list[AlertaSummary]]:
    conn        = _conn()
    cam_total   = conn.execute("SELECT COUNT(*) FROM camaras").fetchone()[0]
    ev_confirma = conn.execute("SELECT COUNT(*) FROM eventos WHERE estado='confirmado'").fetchone()[0]
    ev_desc     = conn.execute("SELECT COUNT(*) FROM eventos WHERE estado='descartado'").fetchone()[0]
    ev_total    = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    conn.close()
    precision = 0
    if ev_confirma + ev_desc > 0:
        precision = int(ev_confirma / (ev_confirma + ev_desc) * 100)
    texto = (
        f"📊 **Estadísticas ARGOS:**\n"
        f"• Cámaras monitoreadas: {cam_total}\n"
        f"• Eventos totales: {_num(ev_total)}\n"
        f"• Evasiones confirmadas: {ev_confirma}\n"
        f"• Precisión del modelo: {precision}%\n"
        f"• FPS de procesamiento: 15.4\n"
        f"• Uptime: 99.7%"
    )
    return texto, []


def _contenido_historico() -> tuple[str, list[AlertaSummary]]:
    conn    = _conn()
    por_tipo = conn.execute(
        "SELECT tipo, COUNT(*) as total FROM eventos GROUP BY tipo ORDER BY total DESC"
    ).fetchall()
    top_est = conn.execute(
        """SELECT c.estacion, COUNT(*) as total
           FROM eventos e JOIN camaras c ON c.id = e.camara_id
           GROUP BY c.estacion ORDER BY total DESC LIMIT 5"""
    ).fetchall()
    conn.close()

    texto = "📈 **Datos históricos:**\n\nEventos por tipo:\n"
    for r in por_tipo:
        texto += f"  · {r['tipo'].capitalize()}: {r['total']}\n"
    texto += "\nTop estaciones con más eventos:\n"
    for i, r in enumerate(top_est, 1):
        texto += f"  {i}. {r['estacion']}: {r['total']}\n"
    return texto.strip(), []


def _contenido_logs() -> tuple[str, list[AlertaSummary]]:
    conn     = _conn()
    recientes = conn.execute(
        """SELECT a.accion, a.detalle, a.fecha, u.username
           FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
           WHERE a.accion IN ('CAMARA_CREADA','CAMARA_ACTUALIZADA','CAMARA_ELIMINADA',
                              'CONFIG_ACTUALIZADA','MODELO_ACTUALIZADO','LOGIN_FALLIDO')
           ORDER BY a.fecha DESC LIMIT 8"""
    ).fetchall()
    conn.close()
    if not recientes:
        return "📋 No hay logs técnicos recientes registrados.", []
    texto = "🔧 **Logs técnicos recientes:**\n"
    for r in recientes:
        hora = r["fecha"][11:16] if r["fecha"] else "--:--"
        user = _sanitize(r["username"] or "sistema")
        texto += f"  · [{hora}] {r['accion']} - {user}"
        if r["detalle"]:
            texto += f" ({_sanitize(r['detalle'][:60])})"
        texto += "\n"
    return texto.strip(), []


def _contenido_usuarios() -> tuple[str, list[AlertaSummary]]:
    conn    = _conn()
    total   = conn.execute("SELECT COUNT(*) FROM usuarios WHERE activo=1").fetchone()[0]
    por_rol = conn.execute(
        "SELECT rol, COUNT(*) as total FROM usuarios WHERE activo=1 GROUP BY rol"
    ).fetchall()
    conn.close()
    texto = f"👥 **Usuarios del sistema ({total} activos):**\n"
    for r in por_rol:
        texto += f"  · {r['rol'].capitalize()}: {r['total']}\n"
    return texto.strip(), []


def _contenido_auditoria() -> tuple[str, list[AlertaSummary]]:
    conn = _conn()
    rows = conn.execute(
        """SELECT a.accion, a.fecha, u.username
           FROM auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
           ORDER BY a.fecha DESC LIMIT 10"""
    ).fetchall()
    conn.close()
    if not rows:
        return "📋 No hay registros de auditoría recientes.", []
    texto = "🔍 **Auditoría reciente (últimas 10 acciones):**\n"
    for r in rows:
        hora = r["fecha"][11:16] if r["fecha"] else "--:--"
        texto += f"  · [{hora}] {r['accion']} - {_sanitize(r['username'] or 'sistema')}\n"
    return texto.strip(), []


def _contenido_rol(usuario: dict) -> tuple[str, list[AlertaSummary]]:
    accesos = {
        "admin":      "Acceso total - configuración, usuarios, IA, infraestructura",
        "supervisor": "Monitoreo completo, alertas, análisis, reportes",
        "operador":   "Monitoreo de cámaras y gestión de alertas en tiempo real",
        "analista":   "Análisis de datos, estadísticas e informes históricos",
        "tecnico":    "IA, infraestructura, configuración y logs técnicos",
        "auditor":    "Auditoría e historial de eventos (solo lectura)",
    }
    texto = (
        f"👤 **Tu sesión activa:**\n"
        f"• Usuario: {_sanitize(usuario['username'])}\n"
        f"• Nombre: {_sanitize(usuario.get('nombre', ''))}\n"
        f"• Rol: {usuario['rol'].upper()}\n"
        f"• Acceso: {accesos.get(usuario['rol'], '-')}"
    )
    return texto, []


def _contenido_ayuda(rol: str) -> tuple[str, list[AlertaSummary]]:
    capacidades = {
        "admin":      ["📡 Estado y métricas del sistema", "📷 Cámaras (ver, crear, editar, eliminar)",
                       "🔔 Alertas y eventos (revisar, exportar)", "📊 Estadísticas e histórico completo",
                       "👥 Usuarios del sistema", "🔧 Logs técnicos y de auditoría"],
        "supervisor": ["📡 Estado del sistema", "📷 Ver cámaras", "🔔 Alertas y eventos",
                       "📊 Estadísticas e histórico", "🔍 Auditoría (vista general)"],
        "operador":   ["📡 Estado del sistema", "📷 Ver cámaras asignadas",
                       "🔔 Alertas pendientes (confirmar / descartar)", "📊 Actividad del día"],
        "analista":   ["📊 Estadísticas completas e histórico", "📷 Ver cámaras (lectura)",
                       "🔔 Ver eventos y exportar"],
        "tecnico":    ["📡 Estado y métricas del sistema", "📷 Cámaras (ver, crear, editar)",
                       "🔧 Logs técnicos detallados", "⚙️ Configuración de IA"],
        "auditor":    ["📷 Ver cámaras (lectura)", "🔔 Ver y exportar eventos",
                       "📊 Estadísticas e histórico", "🔍 Log de auditoría completo"],
    }
    items = capacidades.get(rol, [])
    texto = f"❓ **Soy Hermes, asistente de ARGOS.** Puedo ayudarte con:\n"
    for item in items:
        texto += f"• {item}\n"
    texto += "\nEscribe en lenguaje natural. Ejemplos:\n"
    texto += '"¿Cuántas cámaras están offline?" · "muéstrame las alertas de hoy"'
    return texto.strip(), []


def _contenido_saludo(usuario: dict) -> tuple[str, list[AlertaSummary]]:
    nombre = usuario.get("nombre") or usuario.get("username") or "Usuario"
    texto = (
        f"¡Hola {_sanitize(nombre)}! Soy Hermes, tu asistente inteligente de ARGOS SiViA.\n\n"
        "Puedo informarte sobre el estado del sistema, cámaras, alertas y más. "
        "Recuerda que aun estoy en fase de construcción, así que tengo funciones limitadas."
    )
    return texto, []


# ══════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════

def procesar(
    req: HermesRequest,
    usuario: dict,
    token: str,
) -> HermesResponse:
    """
    Orquesta todo el procesamiento de Hermes IA.

    Args:
        req:     HermesRequest validado por Pydantic
        usuario: dict del usuario autenticado (de request.usuario)
        token:   X-Token del header (para la sesión volátil)

    Returns:
        HermesResponse - siempre tipado, nunca texto crudo
    """
    rol = usuario.get("rol", "")

    # ── 1. Cleanup sesiones expiradas ─────────────────────────
    session_cache.cleanup_expired()

    # ── 2. Motor NLP → intención + entidades ──────────────────
    intent_result = detectar_intencion(
        mensaje=req.mensaje,
        modulo=req.modulo,
        filtros_activos=req.filtros_activos,
    )

    # ── 3. Motor de salud del sistema ─────────────────────────
    snapshot = obtener_snapshot()

    # ── 4. Intenciones libres (siempre accesibles) ────────────
    if intent_result.intent == "ayuda":
        contenido, alertas = _contenido_ayuda(rol)
        tipo     = "ayuda"
        severidad = "normal"

    elif intent_result.intent == "rol":
        contenido, alertas = _contenido_rol(usuario)
        tipo     = "info"
        severidad = "normal"

    elif intent_result.intent == "saludo":
        contenido, alertas = _contenido_saludo(usuario)
        tipo     = "info"
        severidad = "normal"

    elif intent_result.intent == "desconocido":
        contenido = (
            "No entendí completamente tu consulta. "
            "Puedo ayudarte con información sobre **cámaras**, **alertas**, "
            "**estadísticas**, **estado del sistema** o tu **rol y permisos**.\n\n"
            "Escribe **ayuda** para ver todas mis capacidades."
        )
        alertas  = []
        tipo     = "desconocido"
        severidad = "normal"

    else:
        # ── 5. Verificar RBAC ──────────────────────────────────
        permiso_req = INTENT_PERMISSION_MAP.get(intent_result.intent)
        if permiso_req and not tiene_permiso(usuario, permiso_req):
            contenido = (
                f"🔒 **No tienes permisos para esa consulta.**\n"
                f"Tu rol `{rol}` no puede acceder a esa información.\n\n"
                f"Escribe **ayuda** para ver qué consultas puedes realizar."
            )
            alertas  = []
            tipo     = "denegado"
            severidad = "normal"
        else:
            # ── 6. Generar respuesta de BD ─────────────────────
            gen = {
                "estado_sistema": lambda: _contenido_estado_sistema(snapshot),
                "camaras":        _contenido_camaras,
                "alertas":        _contenido_alertas,
                "estadisticas":   _contenido_estadisticas,
                "historico":      _contenido_historico,
                "logs":           _contenido_logs,
                "usuarios":       _contenido_usuarios,
                "auditoria":      _contenido_auditoria,
            }
            generador = gen.get(intent_result.intent)
            if generador:
                contenido, alertas = generador()
            else:
                contenido = "Consulta procesada."
                alertas   = []

            # Determinar tipo y severidad desde snapshot
            tipo = "alerta" if alertas or snapshot.nivel in ("warning", "critical") else "info"
            severidad = snapshot.nivel  # type: ignore[assignment]

    # ── 7. Acciones y sugerencias por rol ──────────────────────
    acciones    = _acciones_por_rol(rol, intent_result.intent)
    sugerencias = SUGERENCIAS_POR_INTENT.get(intent_result.intent, [])

    # ── 8. Guardar turno en sesión ─────────────────────────────
    session_cache.add_turn(token, rol, req.mensaje, contenido)

    # ── 9. Construir y retornar HermesResponse ─────────────────
    return HermesResponse(
        tipo=tipo,
        severidad=severidad,
        contenido=contenido,
        alertas_resumen=alertas,
        acciones=acciones,
        sugerencias=sugerencias,
        estado_sistema=snapshot,
        intencion_detectada=intent_result.intent,
        rol_usuario=rol,
        session_id=token[:16] if token else None,  # abbreviated, not full token
    )
