"""
api/routers/rbac.py
────────────────────────────────────
GET  /api/rbac/permisos          → permisos del usuario actual
GET  /api/rbac/modulos           → módulos accesibles para el usuario
GET  /api/rbac/matriz            → matriz completa (solo admin)
POST /api/rbac/verificar         → verifica un permiso puntual
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from services.auth_service import get_current_user, require_role
from services.rbac import (
    PERMISOS,
    PERMISOS_ROL,
    tiene_permiso,
    obtener_permisos,
    puede_acceder_modulo,
)

router = APIRouter()

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


@router.get("/permisos")
def mis_permisos(usuario: dict = Depends(get_current_user)):
    permisos = obtener_permisos(usuario)
    return JSONResponse(content={
        "rol":      usuario["rol"],
        "usuario":  usuario["username"],
        "permisos": permisos,
        "total":    len(permisos),
    })


@router.get("/modulos")
def modulos_accesibles(usuario: dict = Depends(get_current_user)):
    accesibles = [m for m in MODULOS if puede_acceder_modulo(usuario, m)]
    return JSONResponse(content={
        "rol":     usuario["rol"],
        "modulos": accesibles,
    })


@router.post("/verificar")
async def verificar_permiso(request: Request, usuario: dict = Depends(get_current_user)):
    data = await request.json() if await _has_body(request) else {}

    if "permisos" in data:
        lista = data["permisos"]
        if not isinstance(lista, list):
            return JSONResponse(status_code=400, content={"error": '"permisos" debe ser un array.'})
        resultados = {p: tiene_permiso(usuario, p) for p in lista}
        return JSONResponse(content={"rol": usuario["rol"], "resultados": resultados})

    permiso = data.get("permiso", "").strip()
    if not permiso:
        return JSONResponse(status_code=400, content={"error": 'Se requiere "permiso" o "permisos".'})

    return JSONResponse(content={
        "rol":        usuario["rol"],
        "permiso":    permiso,
        "autorizado": tiene_permiso(usuario, permiso),
    })


@router.get("/matriz")
def matriz_completa(usuario: dict = Depends(require_role("admin"))):
    matriz = {
        rol: sorted(permisos)
        for rol, permisos in PERMISOS_ROL.items()
    }
    return JSONResponse(content={
        "permisos_disponibles": PERMISOS,
        "total_permisos":       len(PERMISOS),
        "roles":                list(PERMISOS_ROL.keys()),
        "matriz":               matriz,
    })


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
