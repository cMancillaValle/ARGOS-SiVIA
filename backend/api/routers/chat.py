"""
api/routers/chat.py
────────────────────────────────────
Endpoints del asistente Hermes IA (Híbrido Local)

POST /api/chat          → Envío de mensaje y generación de respuesta
GET  /api/chat/permisos → Permisos RBAC del usuario autenticado
GET  /api/chat/historial→ Historial volátil de la sesión activa
GET  /api/chat/estado   → Disponibilidad de integración local y Ollama
"""

from fastapi import APIRouter, Request, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import Optional

from services.auth_service import get_current_user, registrar_auditoria
from services.hermes_context import HermesRequest
from services.hermes_service import procesar
from services.ollama_service import ollama_client
from services.hermes_session import session_cache

router = APIRouter()


@router.post("")
async def chat(
    request: Request,
    usuario: dict = Depends(get_current_user),
    x_token: Optional[str] = Header(default="", alias="X-Token"),
):
    raw = await request.json() if await _has_body(request) else {}

    try:
        hermes_req = HermesRequest(**raw)
    except ValidationError as exc:
        errors = exc.errors()
        return JSONResponse(
            status_code=400,
            content={
                "error": "Cuerpo de la petición inválido.",
                "detalle": [
                    {"campo": ".".join(str(l) for l in e["loc"]), "msg": e["msg"]}
                    for e in errors
                ]
            }
        )

    hermes_resp = procesar(hermes_req, usuario, x_token or "")

    ip = request.client.host if request.client else None
    # Auditoría con metadatos mínimos y sin datos sensibles ni prompts completos
    registrar_auditoria(
        usuario["id"], "CHAT_HERMES",
        f"[{usuario['rol']}] modo={hermes_resp.modo or 'general'} intent={hermes_resp.intencion_detectada} tools={len(hermes_resp.herramientas_usadas)}",
        ip
    )

    return JSONResponse(content=hermes_resp.model_dump())


@router.get("/permisos")
def mis_permisos(usuario: dict = Depends(get_current_user)):
    from services.rbac import obtener_permisos
    permisos = obtener_permisos(usuario)
    return JSONResponse(content={
        "rol":      usuario["rol"],
        "permisos": permisos,
    })


@router.get("/historial")
def historial_sesion(
    usuario: dict = Depends(get_current_user),
    x_token: Optional[str] = Header(default="", alias="X-Token"),
    session_id: Optional[str] = None,
):
    session_key = session_cache.derive_key(usuario["id"], session_id=session_id, token=x_token)
    historial = session_cache.get_history(session_key)
    return JSONResponse(content={
        "sesion_activa": bool(historial),
        "turnos":        historial,
        "total":         len(historial),
    })


@router.get("/estado")
def estado_asistente(usuario: dict = Depends(get_current_user)):
    """
    Endpoint autenticado que reporta la disponibilidad del servicio local sin
    exponer URLs, puertos, prompts ni credenciales privadas.
    """
    health = ollama_client.health_check()
    return JSONResponse(content={
        "integracion_local_habilitada": True,
        "ollama_disponible": bool(health.get("disponible", False)),
        "modelo_configurado": health.get("modelo_configurado", "qwen2.5:3b"),
        "modelos_disponibles": health.get("modelos", []),
    })


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
