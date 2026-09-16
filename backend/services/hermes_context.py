"""
services/hermes_context.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Hermes IA - Contratos Pydantic v2

Define los esquemas estrictos de entrada y salida del endpoint /api/chat.
El frontend SIEMPRE envía un HermesRequest y recibe un HermesResponse.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════════
#  TIPOS AUXILIARES
# ══════════════════════════════════════════════════════════════

class AlertaSummary(BaseModel):
    """Resumen compacto de una alerta pendiente."""
    camara_codigo:  str
    estacion:       str
    tipo:           str
    hora:           str        # HH:MM
    confianza_pct:  int        # 0-100


class AccionSugerida(BaseModel):
    """Botón de acción rápida que el frontend puede renderizar."""
    id:         str            # identificador único de la acción
    label:      str            # texto visible del botón
    endpoint:   Optional[str] = None  # ruta API a llamar (si aplica)
    metodo:     Literal["GET", "POST", "PUT", "DELETE"] = "GET"
    payload:    Optional[dict[str, Any]] = None
    permiso_requerido: Optional[str] = None  # permiso RBAC para mostrarla


class SystemHealthSnapshot(BaseModel):
    """Captura del estado de salud del sistema en el momento de la respuesta."""
    nivel:             Literal["normal", "warning", "critical"]
    camaras_total:     int
    camaras_activas:   int
    camaras_offline:   int
    alertas_pendientes: int
    fps_estimado:      float = 15.4
    uptime_pct:        float = 99.7
    evaluado_en:       str   = Field(
        default_factory=lambda: datetime.now().strftime("%H:%M:%S")
    )


# ══════════════════════════════════════════════════════════════
#  CONTRATO DE ENTRADA  (Frontend → Backend)
# ══════════════════════════════════════════════════════════════

class HermesRequest(BaseModel):
    """
    Lo que el frontend envía en el body de POST /api/chat.

    Campos:
        mensaje         Texto libre del usuario (obligatorio)
        modulo          Módulo actual de la UI (opcional, mejora el contexto)
        filtros_activos Filtros de UI activos, ej: {'estacion': 'Suba', 'fecha': 'ayer'}
        session_id      UUID local de sesión del widget (para recuperar historial)
    """
    mensaje:         str = Field(..., min_length=1, max_length=500,
                                 description="Mensaje del usuario")
    modulo:          Optional[str] = Field(None, max_length=50,
                                           description="Módulo activo en la UI")
    filtros_activos: Optional[dict[str, str]] = Field(
        default_factory=dict,
        description="Filtros activos en la pantalla actual"
    )
    session_id:      Optional[str] = Field(None, max_length=64,
                                           description="UUID de sesión del widget")

    @field_validator("mensaje")
    @classmethod
    def sanitize_mensaje(cls, v: str) -> str:
        """Limpieza básica - elimina caracteres de control."""
        return " ".join(v.split())

    @field_validator("modulo")
    @classmethod
    def normalize_modulo(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.strip().lower()
        return v


# ══════════════════════════════════════════════════════════════
#  CONTRATO DE SALIDA  (Backend → Frontend)
# ══════════════════════════════════════════════════════════════

class HermesResponse(BaseModel):
    """
    Lo que /api/chat siempre devuelve - tipado estrictamente.

    Campos:
        tipo             Clasificación semántica de la respuesta
        severidad        Nivel de urgencia visual
        contenido        Texto de la respuesta (markdown-safe)
        alertas_resumen  Lista compacta de alertas relevantes (puede ser vacía)
        acciones         Botones de acción rápida según el rol
        sugerencias      Preguntas de seguimiento sugeridas
        estado_sistema   Snapshot del estado en este momento
        intencion_detectada  Intent que el motor NLP identificó
        rol_usuario      Rol del usuario autenticado
        timestamp        Momento de la respuesta
        session_id       Session ID confirmado/generado
    """
    tipo:               Literal[
                            "info", "alerta", "error",
                            "confirmacion", "denegado", "ayuda", "desconocido"
                        ]
    severidad:          Literal["normal", "warning", "critical"]
    contenido:          str
    alertas_resumen:    list[AlertaSummary]    = Field(default_factory=list)
    acciones:           list[AccionSugerida]   = Field(default_factory=list)
    sugerencias:        list[str]              = Field(default_factory=list)
    estado_sistema:     Optional[SystemHealthSnapshot] = None
    intencion_detectada: str                  = "desconocido"
    rol_usuario:        str                   = ""
    timestamp:          str                   = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    session_id:         Optional[str]         = None
