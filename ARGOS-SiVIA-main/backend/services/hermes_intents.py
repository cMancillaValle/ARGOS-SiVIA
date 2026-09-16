"""
services/hermes_intents.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Hermes IA - Motor NLP Liviano por Reglas

Detecta intenciones y extrae entidades del mensaje del usuario
usando regex y diccionarios temáticos en Python puro.
Sin dependencias de ML - rápido y predecible.

Intenciones reconocidas:
    estado_sistema | camaras | alertas | estadisticas | historico
    logs | usuarios | auditoria | rol | ayuda | saludo | desconocido

Entidades extraíbles:
    fecha_relativa  →  'hoy', 'ayer', 'semana', 'mes'
    ubicacion       →  nombre de estación (cargado desde BD)
    tipo_evento     →  'evasion', 'intrusion', 'merodeo', etc.
    severidad_buscada → 'critica', 'pendiente', etc.
"""

from __future__ import annotations
import re
import os
import sqlite3
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("ARGOS.Intents")

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "database", "argos.db"
))


# ══════════════════════════════════════════════════════════════
#  CACHE DE ESTACIONES (cargado lazy desde BD)
# ══════════════════════════════════════════════════════════════

_estaciones_cache: list[str] = []

def _cargar_estaciones() -> list[str]:
    """Carga nombres de estaciones en memoria (solo una vez)."""
    global _estaciones_cache
    if _estaciones_cache:
        return _estaciones_cache
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT DISTINCT estacion FROM camaras").fetchall()
        conn.close()
        _estaciones_cache = [r[0].lower() for r in rows if r[0]]
    except Exception as exc:
        log.warning(f"No se pudo cargar estaciones: {exc}")
        _estaciones_cache = []
    return _estaciones_cache


# ══════════════════════════════════════════════════════════════
#  DATACLASS DE RESULTADO
# ══════════════════════════════════════════════════════════════

@dataclass
class IntentResult:
    intent:          str   = "desconocido"
    confidence:      float = 0.0          # 0.0 - 1.0
    fecha_relativa:  Optional[str] = None # 'hoy' | 'ayer' | 'semana' | 'mes'
    ubicacion:       Optional[str] = None # nombre de estación
    tipo_evento:     Optional[str] = None # 'evasion' | 'intrusion' | etc.
    severidad_buscada: Optional[str] = None  # 'critica' | 'pendiente'
    keywords_matched: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
#  PATRONES DE INTENCIÓN  (orden importa: más específico primero)
# ══════════════════════════════════════════════════════════════

# Estructura: (intent_name, peso_base, [patrones_regex])
INTENT_PATTERNS: list[tuple[str, float, list[str]]] = [

    ("saludo", 1.0, [
        r"\b(hola|buenos?\s+d[ií]as?|buenas?\s+tardes?|buenas?\s+noches?|qu[eé]\s+tal|buenas|saludos?)\b",
    ]),

    ("ayuda", 1.0, [
        r"\b(ayuda|help|qu[eé]\s+puedes|comandos|qu[eé]\s+haces|capacidades|funciones)\b",
    ]),

    ("rol", 0.95, [
        r"\b(mi\s+rol|mis\s+permisos?|qu[eé]\s+puedo|mi\s+cuenta|mi\s+usuario|mi\s+acceso|soy\s+un)\b",
    ]),

    ("logs", 0.9, [
        r"\b(log[s]?\s+t[eé]cnico[s]?|infraestructura|reinicio[s]?|log\s+del\s+sistema|registros?\s+t[eé]cnico[s]?)\b",
    ]),

    ("auditoria", 0.88, [
        r"\b(auditor[ií]a|trazabilidad|qui[eé]n\s+hizo|historial\s+de\s+acciones?|registro\s+de\s+actividad)\b",
    ]),

    ("usuarios", 0.85, [
        r"\b(usuario[s]?|operadores?|personal|staff|cuántos?\s+usuarios?|listar\s+usuarios?)\b",
    ]),

    ("historico", 0.85, [
        r"\b(hist[oó]rico?|historial|tendencia[s]?|acumulado|pasado|anterior|estad[ií]sticas?\s+histór)\b",
    ]),

    ("estadisticas", 0.82, [
        r"\b(estad[ií]stica[s]?|m[eé]trica[s]?|n[uú]meros?|precisi[oó]n|fps|rendimiento|stat[s]?)\b",
    ]),

    ("alertas", 0.80, [
        r"\b(alerta[s]?|evento[s]?|detecci[oó]n|detecciones|pendiente[s]?|incidente[s]?|notificaci[oó]n[es]?)\b",
    ]),

    ("camaras", 0.80, [
        r"\b(c[aá]mara[s]?|cam|offline|fuera\s+de\s+l[ií]nea|sin\s+se[ñn]al|monitor[eo]|circuito)\b",
    ]),

    ("estado_sistema", 0.75, [
        r"\b(estado|sistema|activo|funcionando|c[oó]mo\s+est[aá]|uptime|operativo|salud\s+del\s+sistema)\b",
    ]),
]


# ══════════════════════════════════════════════════════════════
#  PATRONES DE ENTIDADES
# ══════════════════════════════════════════════════════════════

FECHA_PATTERNS = [
    (r"\b(hoy|este\s+d[ií]a)\b",            "hoy"),
    (r"\b(ayer|d[ií]a\s+anterior)\b",        "ayer"),
    (r"\b(esta\s+semana|[uú]ltimos?\s+7\s+d[ií]as?)\b", "semana"),
    (r"\b([uú]ltimo\s+mes|[uú]ltimos?\s+30\s+d[ií]as?)\b", "mes"),
]

TIPO_EVENTO_PATTERNS = [
    (r"\b(evasi[oó]n|evasiones?)\b",      "evasion"),
    (r"\b(intrusi[oó]n|intrusiones?)\b",   "intrusion"),
    (r"\b(merodeo|merodeadores?)\b",       "merodeo"),
    (r"\b(abandono|objeto\s+abandonado)\b","abandono"),
    (r"\b(aglomeraci[oó]n|muchedumbre)\b", "aglomeracion"),
]

SEVERIDAD_PATTERNS = [
    (r"\b(cr[ií]ticas?|cr[ií]tico[s]?)\b",  "critica"),
    (r"\b(pendiente[s]?|sin\s+revisar)\b",   "pendiente"),
    (r"\b(confirmad[ao]s?)\b",               "confirmada"),
    (r"\b(descartad[ao]s?)\b",               "descartada"),
]


# ══════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════

def detectar_intencion(
    mensaje: str,
    modulo: Optional[str] = None,
    filtros_activos: Optional[dict] = None,
) -> IntentResult:
    """
    Analiza el mensaje y devuelve un IntentResult con la intención
    detectada y las entidades extraídas.

    Estrategia:
    1. Normalizar texto (lower, sin tildes opcionales)
    2. Boosting de contexto: si el módulo activo menciona 'camaras',
       subir el score de intent 'camaras'
    3. Iterar patrones en orden de peso y acumular matches
    4. El intent con mayor score gana
    5. Extraer entidades independientemente del intent ganador
    """
    texto = mensaje.lower()
    # Añadir módulo como contexto extra (igual que el código anterior)
    if modulo:
        texto = f"{modulo.lower()} {texto}"
    # Añadir pistas de filtros activos
    if filtros_activos:
        claves = " ".join(filtros_activos.values()).lower()
        texto = f"{claves} {texto}"

    result = IntentResult()

    # ── Evaluar cada intent ─────────────────────────────────
    scores: dict[str, float] = {}
    matched_kw: dict[str, list[str]] = {}

    for intent_name, peso_base, patterns in INTENT_PATTERNS:
        score = 0.0
        kws: list[str] = []
        for pat in patterns:
            found = re.findall(pat, texto, re.IGNORECASE)
            if found:
                score += peso_base
                kws.extend(found if isinstance(found[0], str) else [f[0] for f in found])
        if score > 0:
            scores[intent_name] = score
            matched_kw[intent_name] = kws

    # ── Determinar ganador ──────────────────────────────────
    if scores:
        best_intent = max(scores, key=lambda k: scores[k])
        result.intent     = best_intent
        result.confidence = min(scores[best_intent], 1.0)
        result.keywords_matched = matched_kw.get(best_intent, [])
    else:
        result.intent     = "desconocido"
        result.confidence = 0.0

    # ── Extraer entidades ───────────────────────────────────
    for pat, valor in FECHA_PATTERNS:
        if re.search(pat, texto, re.IGNORECASE):
            result.fecha_relativa = valor
            break

    for pat, valor in TIPO_EVENTO_PATTERNS:
        if re.search(pat, texto, re.IGNORECASE):
            result.tipo_evento = valor
            break

    for pat, valor in SEVERIDAD_PATTERNS:
        if re.search(pat, texto, re.IGNORECASE):
            result.severidad_buscada = valor
            break

    # ── Ubicación: buscar nombre de estación en texto ───────
    estaciones = _cargar_estaciones()
    for est in estaciones:
        if est in texto:
            result.ubicacion = est
            break

    return result
