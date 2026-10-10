"""
api/routers/sesiones.py
────────────────────────────────────
GET  /api/sesiones/activas   → Usuarios conectados ahora + módulo actual
POST /api/sesiones/modulo    → El frontend reporta el módulo que el usuario está viendo
"""

from fastapi import APIRouter, Request, Depends, Header
from fastapi.responses import JSONResponse
from typing import Optional

from services.auth_service import (
    get_current_user, require_permission,
    actualizar_modulo_sesion, listar_sesiones_activas,
)

router = APIRouter()


@router.get("/activas")
def sesiones_activas(usuario: dict = Depends(require_permission("auditoria:ver"))):
    """Lista de usuarios conectados en este momento y su módulo actual."""
    sesiones = listar_sesiones_activas()
    return JSONResponse(content={
        'total': len(sesiones),
        'sesiones': sesiones,
    })


@router.post("/modulo")
async def reportar_modulo(
    request: Request,
    usuario: dict = Depends(get_current_user),
    x_token: Optional[str] = Header(default=None, alias="X-Token"),
):
    """
    Body JSON: { "modulo": "camaras" }
    Actualiza el módulo activo de la sesión del usuario autenticado.
    """
    data   = await request.json() if await _has_body(request) else {}
    modulo = data.get('modulo', '').strip()

    if not modulo:
        return JSONResponse(status_code=400, content={'error': 'El campo "modulo" es obligatorio.'})

    if not x_token:
        return JSONResponse(status_code=400, content={'error': 'Token no encontrado en cabecera.'})

    ok = actualizar_modulo_sesion(x_token, modulo)
    if not ok:
        return JSONResponse(status_code=400, content={'error': 'No se pudo actualizar la sesión.'})

    return JSONResponse(content={'status': 'ok'})


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
