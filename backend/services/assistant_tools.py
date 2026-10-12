"""
services/assistant_tools.py
────────────────────────────────────────────────────────────
Herramientas backend explícitas y deterministas para Hermes IA.

REGLAS DE SEGURIDAD:
1. Toda consulta a la BD SQLite está parametrizada estrictamente.
2. Se verifica RBAC antes de consultar cualquier dato.
3. Se utiliza la zona horaria America/Bogota para cálculos temporales.
4. Qwen NUNCA genera SQL ni accede a la base de datos directamente.
"""

from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timedelta, date
from typing import Any, Optional, Dict, List

try:
    from zoneinfo import ZoneInfo
    BOGOTA_TZ = ZoneInfo("America/Bogota")
except Exception:
    # Fallback para Windows o entornos donde no esté el paquete tzdata instalado
    from datetime import timezone
    BOGOTA_TZ = timezone(timedelta(hours=-5))

from services.rbac import tiene_permiso

DB_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "database", "argos.db"
))


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_bogota() -> datetime:
    """Devuelve la fecha/hora actual en zona horaria America/Bogota."""
    return datetime.now(BOGOTA_TZ)


# ══════════════════════════════════════════════════════════════
#  1. CONSULTA DE EVENTOS / DETECCIONES (ANÁLISIS)
# ══════════════════════════════════════════════════════════════

def obtener_evento_por_id(evento_id: int, usuario: dict) -> Optional[Dict[str, Any]]:
    """
    Recupera un evento/análisis por su ID con verificación de permisos RBAC.
    Retorna None si no existe o el usuario no tiene permisos.
    """
    if not tiene_permiso(usuario, "eventos:ver"):
        return None

    try:
        eid = int(evento_id)
    except (ValueError, TypeError):
        return None

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.tipo, e.confianza, e.estado, e.observaciones,
               e.detectado_en, e.revisado_en, e.evidencia,
               c.codigo as camara_codigo, c.estacion, c.ubicacion,
               u.nombre as operador_nombre
        FROM eventos e
        JOIN camaras c ON c.id = e.camara_id
        LEFT JOIN usuarios u ON u.id = e.operador_id
        WHERE e.id = ?
    """, (eid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    confianza_pct = int(round(float(row["confianza"]) * 100))
    return {
        "id": row["id"],
        "tipo": row["tipo"],
        "confianza": float(row["confianza"]),
        "confianza_pct": confianza_pct,
        "estado": row["estado"],
        "observaciones": row["observaciones"] or "Sin observaciones registradas",
        "detectado_en": row["detectado_en"],
        "revisado_en": row["revisado_en"] or "Pendiente de revisión",
        "camara_codigo": row["camara_codigo"],
        "estacion": row["estacion"],
        "ubicacion": row["ubicacion"],
        "operador": row["operador_nombre"] or "No asignado",
        "tiene_evidencia": bool(row["evidencia"]),
    }


def obtener_ultimo_evento_de_camara(camara_codigo_o_id: str, usuario: dict) -> Optional[Dict[str, Any]]:
    """
    Recupera el evento más reciente asociado a una cámara específica.
    """
    if not tiene_permiso(usuario, "eventos:ver"):
        return None

    identificador = str(camara_codigo_o_id).strip().upper()
    if not identificador:
        return None

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.tipo, e.confianza, e.estado, e.observaciones,
               e.detectado_en, e.revisado_en,
               c.codigo as camara_codigo, c.estacion, c.ubicacion
        FROM eventos e
        JOIN camaras c ON c.id = e.camara_id
        WHERE UPPER(c.codigo) = ? OR c.id = ?
        ORDER BY e.detectado_en DESC
        LIMIT 1
    """, (identificador, identificador))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    confianza_pct = int(round(float(row["confianza"]) * 100))
    return {
        "id": row["id"],
        "tipo": row["tipo"],
        "confianza": float(row["confianza"]),
        "confianza_pct": confianza_pct,
        "estado": row["estado"],
        "observaciones": row["observaciones"] or "Sin observaciones",
        "detectado_en": row["detectado_en"],
        "camara_codigo": row["camara_codigo"],
        "estacion": row["estacion"],
        "ubicacion": row["ubicacion"],
    }


def obtener_ultimo_evento_global(usuario: dict) -> Optional[Dict[str, Any]]:
    """
    Recupera el evento/análisis más reciente registrado en todo el sistema.
    Requiere permiso eventos:ver.
    """
    if not tiene_permiso(usuario, "eventos:ver"):
        return None

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.tipo, e.confianza, e.estado, e.observaciones,
               e.detectado_en, e.revisado_en, e.evidencia,
               c.codigo as camara_codigo, c.estacion, c.ubicacion,
               u.nombre as operador_nombre
        FROM eventos e
        JOIN camaras c ON c.id = e.camara_id
        LEFT JOIN usuarios u ON u.id = e.operador_id
        ORDER BY e.detectado_en DESC, e.id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    confianza_pct = int(round(float(row["confianza"]) * 100))
    return {
        "id": row["id"],
        "tipo": row["tipo"],
        "confianza": float(row["confianza"]),
        "confianza_pct": confianza_pct,
        "estado": row["estado"],
        "observaciones": row["observaciones"] or "Sin observaciones",
        "detectado_en": row["detectado_en"],
        "revisado_en": row["revisado_en"] or "Pendiente de revisión",
        "camara_codigo": row["camara_codigo"],
        "estacion": row["estacion"],
        "ubicacion": row["ubicacion"],
        "operador": row["operador_nombre"] or "No asignado",
        "tiene_evidencia": bool(row["evidencia"]),
    }


def buscar_camaras(termino: str, usuario: dict) -> Dict[str, Any]:
    """
    Busca cámaras por código, nombre/ubicación, o estación (coincidencia parcial o exacta).
    Requiere camaras:ver.
    """
    if not tiene_permiso(usuario, "camaras:ver"):
        return {"error": "permiso_denegado", "permiso_requerido": "camaras:ver"}

    termino_clean = (termino or "").strip()
    if not termino_clean:
        return {"total": 0, "camaras": [], "termino_buscado": ""}

    param = f"%{termino_clean}%"
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, codigo, estacion, codigo_estacion, ubicacion, estado, fps, resolucion, ip
        FROM camaras
        WHERE codigo LIKE ? OR estacion LIKE ? OR ubicacion LIKE ? OR codigo_estacion LIKE ?
        ORDER BY codigo ASC
        LIMIT 20
    """, (param, param, param, param))
    filas = cursor.fetchall()
    conn.close()

    camaras = [
        {
            "id": r["id"],
            "codigo": r["codigo"],
            "estacion": r["estacion"],
            "codigo_estacion": r["codigo_estacion"],
            "ubicacion": r["ubicacion"],
            "estado": r["estado"],
            "fps": r["fps"],
            "resolucion": r["resolucion"],
        }
        for r in filas
    ]
    return {
        "termino_buscado": termino_clean,
        "encontradas": len(camaras),
        "camaras": camaras
    }


def obtener_resumen_camaras(usuario: dict) -> Dict[str, Any]:
    """
    Obtiene el resumen y listado de cámaras del sistema: total, activas, offline, mantenimiento.
    Requiere camaras:ver.
    """
    if not tiene_permiso(usuario, "camaras:ver"):
        return {"error": "permiso_denegado", "permiso_requerido": "camaras:ver"}

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN estado = 'activa' THEN 1 ELSE 0 END) as activas,
            SUM(CASE WHEN estado = 'offline' THEN 1 ELSE 0 END) as offline,
            SUM(CASE WHEN estado = 'mantenimiento' THEN 1 ELSE 0 END) as mantenimiento
        FROM camaras
    """)
    res = cursor.fetchone()

    cursor.execute("""
        SELECT id, codigo, estacion, ubicacion, estado
        FROM camaras
        ORDER BY codigo ASC
        LIMIT 25
    """)
    lista = [
        {
            "codigo": r["codigo"],
            "estacion": r["estacion"],
            "ubicacion": r["ubicacion"],
            "estado": r["estado"]
        }
        for r in cursor.fetchall()
    ]
    conn.close()

    total = res["total"] or 0
    activas = res["activas"] or 0
    offline = res["offline"] or 0
    mantenimiento = res["mantenimiento"] or 0

    return {
        "total": total,
        "activas": activas,
        "offline": offline,
        "mantenimiento": mantenimiento,
        "camaras_muestra": lista
    }


def obtener_usuarios_resumen(usuario: dict) -> Dict[str, Any]:
    """
    Consulta usuarios activos y resumen por rol sin exponer contraseñas, emails o datos sensibles.
    Requiere usuarios:ver.
    """
    if not tiene_permiso(usuario, "usuarios:ver"):
        return {"error": "permiso_denegado", "permiso_requerido": "usuarios:ver"}

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN activo = 1 THEN 1 ELSE 0 END) as activos,
            SUM(CASE WHEN activo = 0 THEN 1 ELSE 0 END) as inactivos
        FROM usuarios
    """)
    totales = cursor.fetchone()

    cursor.execute("""
        SELECT rol, COUNT(*) as cantidad
        FROM usuarios
        WHERE activo = 1
        GROUP BY rol
        ORDER BY cantidad DESC
    """)
    roles = {r["rol"]: r["cantidad"] for r in cursor.fetchall()}

    cursor.execute("""
        SELECT username, nombre, rol, activo
        FROM usuarios
        WHERE activo = 1
        ORDER BY id ASC
        LIMIT 15
    """)
    usuarios_lista = [
        {"username": r["username"], "nombre": r["nombre"], "rol": r["rol"]}
        for r in cursor.fetchall()
    ]
    conn.close()

    return {
        "total": totales["total"] or 0,
        "activos": totales["activos"] or 0,
        "inactivos": totales["inactivos"] or 0,
        "por_rol": roles,
        "usuarios_activos_muestra": usuarios_lista
    }


def obtener_actividad_auditoria(usuario: dict, limite: int = 5) -> Dict[str, Any]:
    """
    Consulta los registros recientes del log de auditoría sin exponer tokens ni IPs sensibles.
    Requiere auditoria:ver.
    """
    if not tiene_permiso(usuario, "auditoria:ver"):
        return {"error": "permiso_denegado", "permiso_requerido": "auditoria:ver"}

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.accion, a.detalle, a.fecha, u.username, u.rol
        FROM auditoria a
        LEFT JOIN usuarios u ON u.id = a.usuario_id
        ORDER BY a.fecha DESC, a.id DESC
        LIMIT ?
    """, (min(max(limite, 1), 20),))
    filas = cursor.fetchall()
    conn.close()

    registros = []
    for r in filas:
        registros.append({
            "id": r["id"],
            "accion": r["accion"],
            "detalle": r["detalle"],
            "fecha": r["fecha"],
            "usuario": r["username"] or "sistema",
            "rol": r["rol"] or "-"
        })

    return {
        "total_consultado": len(registros),
        "registros": registros
    }


def obtener_metricas_infraestructura(usuario: dict) -> Dict[str, Any]:
    """
    Obtiene métricas de CPU, RAM, disco, red, uptime y GPU directamente
    reutilizando las funciones de api/routers/system_metrics.py sin llamadas HTTP internas.
    Requiere sistema:ver_metricas o sistema:ver_estado.
    """
    if not (tiene_permiso(usuario, "sistema:ver_metricas") or tiene_permiso(usuario, "sistema:ver_estado")):
        return {"error": "permiso_denegado", "permiso_requerido": "sistema:ver_metricas"}

    try:
        from api.routers.system_metrics import (
            _get_cpu, _get_ram, _get_disco, _get_red, _get_gpu, _get_uptime
        )
        cpu = _get_cpu()
        ram = _get_ram()
        disco = _get_disco()
        red = _get_red()
        gpu = _get_gpu()
        uptime = _get_uptime()
    except Exception as e:
        return {
            "error": "error_lectura",
            "detalle": str(e)
        }

    ahora = _now_bogota()
    return {
        "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "zona_horaria": "America/Bogota",
        "uptime": uptime or "No disponible",
        "cpu": cpu,
        "ram": ram,
        "disco": disco,
        "red": red,
        "gpu": gpu
    }


def explicar_concepto_de_confianza(confianza_val: Optional[float] = None) -> Dict[str, Any]:
    """
    Genera la base conceptual de lo que representa un valor de confianza.
    """
    pct = int(round(confianza_val * 100)) if confianza_val is not None else None
    return {
        "concepto": "Nivel de Confianza (Confidence Score)",
        "rango": "0.0 a 1.0 (0% a 100%)",
        "valor_consultado": pct,
        "umbral_deteccion_defecto": "50% (ia_confidence_threshold = 0.50)",
        "interpretacion": (
            "Cuantifica la certidumbre probabilística con la que los modelos de visión artificial "
            "(YOLOv8 para detección de personas y MediaPipe Pose para alineación de extremidades) "
            "asignan una postura y trayectoria al patrón de evasión observado. "
            "Una confianza alta no equivale por sí sola a certeza absoluta ni a culpabilidad legal; "
            "el sistema opera en modo de asistencia y requiere verificación humana por un operador."
        )
    }


# ══════════════════════════════════════════════════════════════
#  2. CONSULTAS DE ESTADÍSTICAS (SQL PARAMETRIZADO + BOGOTA TZ)
# ══════════════════════════════════════════════════════════════

def consultar_estadisticas_eventos(periodo: str, usuario: dict) -> Optional[Dict[str, Any]]:
    """
    Calcula estadísticas agregadas verificando permisos de lectura de eventos/estadísticas.
    Periodos: 'hoy', 'ayer', 'esta_semana', 'semana_anterior', 'pendientes', 'top_camaras'.
    """
    if not (tiene_permiso(usuario, "estadisticas:ver") or tiene_permiso(usuario, "eventos:ver")):
        return None

    ahora = _now_bogota()
    hoy_date = ahora.date()

    conn = _get_db()
    cursor = conn.cursor()

    if periodo == "pendientes":
        cursor.execute("SELECT COUNT(*) FROM eventos WHERE estado = 'pendiente'")
        pendientes = cursor.fetchone()[0]
        cursor.execute("""
            SELECT c.codigo, COUNT(e.id) as total
            FROM eventos e
            JOIN camaras c ON c.id = e.camara_id
            WHERE e.estado = 'pendiente'
            GROUP BY c.codigo
            ORDER BY total DESC LIMIT 3
        """)
        top_pendientes = [{"camara": r[0], "total": r[1]} for r in cursor.fetchall()]
        conn.close()
        return {
            "periodo": "alertas_pendientes",
            "descripcion": "Alertas que requieren revisión de operadores",
            "total_pendientes": pendientes,
            "camaras_con_mas_pendientes": top_pendientes,
            "zona_horaria": "America/Bogota",
            "fecha_consulta": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        }

    elif periodo == "top_camaras":
        hace_7_dias = (ahora - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT c.codigo, c.estacion, COUNT(e.id) as total_eventos
            FROM eventos e
            JOIN camaras c ON c.id = e.camara_id
            WHERE e.detectado_en >= ?
            GROUP BY c.id
            ORDER BY total_eventos DESC
            LIMIT 5
        """, (hace_7_dias,))
        filas = cursor.fetchall()
        conn.close()
        return {
            "periodo": "top_camaras_ultimos_7_dias",
            "descripcion": "Cámaras con mayor número de detecciones en los últimos 7 días",
            "ranking": [
                {"camara": r[0], "estacion": r[1], "eventos": r[2]}
                for r in filas
            ],
            "zona_horaria": "America/Bogota",
        }

    # Rangos por fechas
    if periodo == "hoy":
        fecha_inicio = f"{hoy_date.isoformat()} 00:00:00"
        fecha_fin = f"{hoy_date.isoformat()} 23:59:59"
        periodo_desc = f"Hoy ({hoy_date.isoformat()})"
    elif periodo == "ayer":
        ayer_date = hoy_date - timedelta(days=1)
        fecha_inicio = f"{ayer_date.isoformat()} 00:00:00"
        fecha_fin = f"{ayer_date.isoformat()} 23:59:59"
        periodo_desc = f"Ayer ({ayer_date.isoformat()})"
    elif periodo == "esta_semana":
        # Lunes de la semana actual
        lunes = hoy_date - timedelta(days=hoy_date.weekday())
        domingo = lunes + timedelta(days=6)
        fecha_inicio = f"{lunes.isoformat()} 00:00:00"
        fecha_fin = f"{domingo.isoformat()} 23:59:59"
        periodo_desc = f"Esta semana ({lunes.isoformat()} al {domingo.isoformat()})"
    elif periodo == "semana_anterior":
        lunes_esta = hoy_date - timedelta(days=hoy_date.weekday())
        lunes_ant = lunes_esta - timedelta(days=7)
        domingo_ant = lunes_ant + timedelta(days=6)
        fecha_inicio = f"{lunes_ant.isoformat()} 00:00:00"
        fecha_fin = f"{domingo_ant.isoformat()} 23:59:59"
        periodo_desc = f"Semana anterior ({lunes_ant.isoformat()} al {domingo_ant.isoformat()})"
    else:
        # Por defecto: hoy
        fecha_inicio = f"{hoy_date.isoformat()} 00:00:00"
        fecha_fin = f"{hoy_date.isoformat()} 23:59:59"
        periodo_desc = f"Hoy ({hoy_date.isoformat()})"

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as confirmados,
            SUM(CASE WHEN estado = 'descartado' THEN 1 ELSE 0 END) as descartados,
            SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) as pendientes
        FROM eventos
        WHERE detectado_en >= ? AND detectado_en <= ?
    """, (fecha_inicio, fecha_fin))
    row = cursor.fetchone()
    conn.close()

    total = row["total"] or 0
    confirmados = row["confirmados"] or 0
    descartados = row["descartados"] or 0
    pendientes = row["pendientes"] or 0

    return {
        "periodo": periodo,
        "descripcion": periodo_desc,
        "rango_inicio": fecha_inicio,
        "rango_fin": fecha_fin,
        "total_eventos": total,
        "confirmados": confirmados,
        "descartados": descartados,
        "pendientes": pendientes,
        "zona_horaria": "America/Bogota",
        "calculado_en": ahora.strftime("%Y-%m-%d %H:%M:%S"),
    }
