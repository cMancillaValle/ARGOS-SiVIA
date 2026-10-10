"""
routes/chat.py  (Hermes IA - refactorizado v2)
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Endpoint del chatbot Hermes IA

La lógica está completamente en services/hermes_service.py.
Esta ruta solo valida el body (Pydantic), delega el procesamiento
y retorna el contrato JSON estructurado.

POST /api/chat
    Body:    HermesRequest  { "mensaje", "modulo"?, "filtros_activos"?, "session_id"? }
    Retorna: HermesResponse { "tipo", "severidad", "contenido", "alertas_resumen",
                              "acciones", "sugerencias", "estado_sistema",
                              "intencion_detectada", "rol_usuario", "timestamp" }

GET /api/chat/permisos
    Retorna: { "rol", "permisos": [...] }
"""

from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from services.auth_service   import requiere_auth, registrar_auditoria
from services.hermes_context import HermesRequest
from services.hermes_service import procesar

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("", methods=["POST"])
@requiere_auth
def chat():
    """
    Endpoint principal de Hermes IA.
    Valida el body con Pydantic → delega a hermes_service.procesar()
    → retorna HermesResponse como JSON.
    """
    raw  = request.get_json(silent=True) or {}

    # ── Validación de entrada con Pydantic ────────────────────
    try:
        hermes_req = HermesRequest(**raw)
    except ValidationError as exc:
        errors = exc.errors()
        return jsonify({
            "error": "Cuerpo de la petición inválido.",
            "detalle": [
                {"campo": ".".join(str(l) for l in e["loc"]), "msg": e["msg"]}
                for e in errors
            ]
        }), 400

    usuario = request.usuario
    token   = request.headers.get("X-Token", "")

    # ── Procesar ──────────────────────────────────────────────
    hermes_resp = procesar(hermes_req, usuario, token)

    # ── Auditoría ─────────────────────────────────────────────
    registrar_auditoria(
        usuario["id"], "CHAT_HERMES",
        f"[{usuario['rol']}] intent={hermes_resp.intencion_detectada} | {hermes_req.mensaje[:80]}"
    )

    return jsonify(hermes_resp.model_dump()), 200


@chat_bp.route("/permisos", methods=["GET"])
@requiere_auth
def mis_permisos():
    """
    GET /api/chat/permisos
    Devuelve la lista de permisos del usuario autenticado.
    El frontend puede usarla para mostrar/ocultar elementos de UI.
    """
    from services.rbac import obtener_permisos
    usuario  = request.usuario
    permisos = obtener_permisos(usuario)
    return jsonify({
        "rol":      usuario["rol"],
        "permisos": permisos,
    })


@chat_bp.route("/historial", methods=["GET"])
@requiere_auth
def historial_sesion():
    """
    GET /api/chat/historial
    Devuelve el historial breve de la sesión actual (últimos MAX_TURNS turnos).
    Útil para que el widget pueda restaurar el chat al recargar dentro de la misma sesión.
    """
    from services.hermes_session import session_cache
    token    = request.headers.get("X-Token", "")
    historial = session_cache.get_history(token)
    return jsonify({
        "sesion_activa": bool(historial),
        "turnos":        historial,
        "total":         len(historial),
    })
