"""
api/routers/chat.py
────────────────────────────────────
Endpoint del chatbot Hermes IA

POST /api/chat
GET  /api/chat/permisos
GET  /api/chat/historial
"""

from fastapi import APIRouter, Request, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import Optional

from services.auth_service import get_current_user, registrar_auditoria
from services.hermes_context import HermesRequest
from services.hermes_service import procesar

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
    registrar_auditoria(
        usuario["id"], "CHAT_HERMES",
        f"[{usuario['rol']}] intent={hermes_resp.intencion_detectada} | {hermes_req.mensaje[:80]}",
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
):
    from services.hermes_session import session_cache
    historial = session_cache.get_history(x_token or "")
    return JSONResponse(content={
        "sesion_activa": bool(historial),
        "turnos":        historial,
        "total":         len(historial),
    })


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
