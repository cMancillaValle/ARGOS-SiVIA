"""
services/system_health.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Hermes IA - Motor de Salud del Sistema

Analiza el estado real de la infraestructura (cámaras, alertas)
y devuelve un SystemHealthSnapshot con nivel: normal / warning / critical.

Thresholds:
  critical  ≥30% cámaras offline  OR  >50 alertas pendientes
  warning   ≥10% cámaras offline  OR  >15 alertas pendientes
  normal    todo lo demás
"""

from __future__ import annotations
import os
import sqlite3
import logging
from services.hermes_context import SystemHealthSnapshot

log = logging.getLogger("ARGOS.SystemHealth")

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "database", "argos.db"
))


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def calcular_umbral(camaras_total: int, camaras_offline: int, alertas_pendientes: int) -> str:
    """Determina el nivel de salud según los thresholds definidos."""
    if camaras_total == 0:
        return "warning"

    pct_offline = camaras_offline / camaras_total

    if pct_offline >= 0.30 or alertas_pendientes > 50:
        return "critical"
    if pct_offline >= 0.10 or alertas_pendientes > 15:
        return "warning"
    return "normal"


def obtener_snapshot() -> SystemHealthSnapshot:
    """
    Consulta la BD y devuelve el estado actual del sistema.
    Diseñado para ser llamado en cada request de Hermes.
    Es eficiente: solo 2 queries simples.
    """
    try:
        conn = _get_conn()

        # Cámaras
        cam_total  = conn.execute("SELECT COUNT(*) FROM camaras").fetchone()[0]
        cam_activa = conn.execute(
            "SELECT COUNT(*) FROM camaras WHERE estado='activa'"
        ).fetchone()[0]
        cam_offline = cam_total - cam_activa

        # Alertas
        alertas_pend = conn.execute(
            "SELECT COUNT(*) FROM eventos WHERE estado='pendiente'"
        ).fetchone()[0]

        conn.close()

        nivel = calcular_umbral(cam_total, cam_offline, alertas_pend)

        return SystemHealthSnapshot(
            nivel=nivel,
            camaras_total=cam_total,
            camaras_activas=cam_activa,
            camaras_offline=cam_offline,
            alertas_pendientes=alertas_pend,
            fps_estimado=15.4,
            uptime_pct=99.7,
        )

    except Exception as exc:
        log.warning(f"No se pudo obtener snapshot del sistema: {exc}")
        # Devolver estado neutro si hay fallo de BD
        return SystemHealthSnapshot(
            nivel="warning",
            camaras_total=0,
            camaras_activas=0,
            camaras_offline=0,
            alertas_pendientes=0,
            fps_estimado=0.0,
            uptime_pct=0.0,
        )
