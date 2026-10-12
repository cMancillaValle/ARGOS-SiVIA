"""
services/assistant_orchestrator.py
────────────────────────────────────────────────────────────
Orquestador híbrido del Asistente Hermes IA con Qwen 2.5 3B local.

Arquitectura:
1. Clasificación determinista de intenciones y entidades.
2. Verificación estricta de RBAC antes de consultar datos.
3. Ejecución de herramientas locales deterministas (Python + SQLite + psutil).
4. Respuestas factuales inmediatas sin LLM para consultas de datos/conteos/infraestructura.
5. Invocación de Ollama (Qwen 2.5 3B) solo para explicaciones, conceptos y documentación.
6. Medición de tiempos de ejecución por etapas y registro seguro en logs.
7. Metadatos de etapas y latencias preservando retrocompatibilidad estricta.
"""

from __future__ import annotations
import re
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple

from services.hermes_context import (
    HermesRequest, HermesResponse,
    AlertaSummary, AccionSugerida, SystemHealthSnapshot,
    FuenteAsistente
)
from services.hermes_session import session_cache
from services.rbac import tiene_permiso
from services.system_health import obtener_snapshot
from services.assistant_tools import (
    obtener_evento_por_id,
    obtener_ultimo_evento_de_camara,
    obtener_ultimo_evento_global,
    buscar_camaras,
    obtener_resumen_camaras,
    obtener_usuarios_resumen,
    obtener_actividad_auditoria,
    obtener_metricas_infraestructura,
    explicar_concepto_de_confianza,
    consultar_estadisticas_eventos,
)
from services.doc_retriever import recuperar_documentacion
from services.ollama_service import ollama_client, OllamaChatResult
from services.assistant_prompts import (
    PROMPT_MODO_GENERAL,
    PROMPT_MODO_VISION,
    PROMPT_MODO_DOCUMENTACION,
    PROMPT_MODO_ESTADISTICAS,
    construir_bloque_contexto,
)

log = logging.getLogger("ARGOS.AssistantOrchestrator")


class AssistantOrchestrator:
    """Orquestador principal del asistente híbrido Hermes IA."""

    def __init__(self):
        self.ollama = ollama_client

    def procesar(self, req: HermesRequest, usuario: dict, token: str) -> HermesResponse:
        t0 = time.perf_counter()
        etapas: List[str] = ["clasificando_consulta"]
        tiempos: Dict[str, float] = {}

        session_cache.cleanup_expired()

        user_id = usuario.get("id", 0)
        user_rol = usuario.get("rol", "operador")
        session_key = session_cache.derive_key(user_id, req.session_id, token)

        mensaje = req.mensaje.strip()
        t_c0 = time.perf_counter()
        modo, metadata = self._clasificar_modo_y_entidades(mensaje)
        tiempos["clasificacion_ms"] = round((time.perf_counter() - t_c0) * 1000, 2)

        snapshot: SystemHealthSnapshot = obtener_snapshot()

        # Enrutamiento según el modo clasificado
        if modo == "eventos" or modo == "vision":
            return self._manejar_modo_eventos_y_vision(
                mensaje, metadata, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "camaras":
            return self._manejar_modo_camaras(
                mensaje, metadata, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "infraestructura" or modo == "sistema":
            return self._manejar_modo_infraestructura(
                mensaje, metadata, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "usuarios":
            return self._manejar_modo_usuarios(
                mensaje, metadata, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "auditoria":
            return self._manejar_modo_auditoria(
                mensaje, metadata, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "estadisticas":
            return self._manejar_modo_estadisticas(
                mensaje, metadata, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "documentacion":
            return self._manejar_modo_documentacion(
                mensaje, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        elif modo == "ayuda":
            return self._manejar_modo_ayuda(
                mensaje, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

        else:
            return self._manejar_modo_general(
                mensaje, usuario, user_rol, session_key, snapshot, etapas, tiempos, t0
            )

    # ══════════════════════════════════════════════════════════════
    #  CLASIFICADOR DE MODOS POR REGLAS DETERMINISTAS
    # ══════════════════════════════════════════════════════════════

    def _clasificar_modo_y_entidades(self, msg: str) -> Tuple[str, Dict[str, Any]]:
        m = msg.lower()

        # 1. Ayuda y capacidades de Hermes
        if any(w in m for w in ("que puedes hacer", "qué puedes hacer", "ayuda", "capacidades", "comandos", "que sabes hacer")):
            return "ayuda", {}

        # 2. Auditoría / Logs de auditoría
        if any(w in m for w in ("auditoria", "auditoría", "actividad reciente", "log de auditoria", "log de auditoría", "logs de auditoria", "logs de auditoría", "quien accedio", "quién accedió", "acciones recientes")):
            return "auditoria", {}

        # 3. Infraestructura y métricas de hardware
        if any(w in m for w in ("cpu", "ram", "disco", "red", "gpu", "hardware", "temperatura", "infraestructura", "uptime", "servidores", "memoria")):
            return "infraestructura", {}

        # 4. Estado general del sistema / salud
        if any(w in m for w in ("estado del sistema", "salud del sistema", "como esta el sistema", "cómo está el sistema", "estado general")):
            return "infraestructura", {}

        # 5. Usuarios del sistema (Solo consultas directas de gestión de usuarios)
        if any(w in m for w in ("cuantos usuarios", "cuántos usuarios", "usuarios activos", "lista de usuarios", "listado de usuarios", "resumen de usuarios", "quien esta conectado", "quién está conectado", "roles de usuarios")):
            return "usuarios", {}
        if ("usuario" in m or "usuarios" in m) and any(w in m for w in ("activos", "roles", "total", "sistema", "cuantos", "cuántos", "hay", "lista", "ver")):
            if not any(w in m for w in ("evento", "camara", "cámara", "contraseña", "contraseñas", "hashes", "ignora", "actúa")):
                return "usuarios", {}

        # 6. Cámaras: Conteo o resumen general PRIMERO
        if any(w in m for w in ("cuantas camaras", "cuántas cámaras", "total de camaras", "total de cámaras", "lista de camaras", "listado de camaras", "camaras activas", "cámaras activas", "camaras offline", "cámaras offline", "camaras en mantenimiento", "cámaras en mantenimiento")):
            return "camaras", {"tipo": "resumen"}

        if m in ("camaras", "cámaras", "ver camaras", "ver cámaras"):
            return "camaras", {"tipo": "resumen"}

        # Cámaras: Búsqueda específica
        # Ejemplos: "¿Existe una cámara llamada Chavi?", "busca la cámara CAM-001"
        if ("camara" in m or "cámara" in m or "cam" in m) and any(w in m for w in ("existe", "llamada", "busca", "buscar", "chavi", "donde esta", "dónde está")):
            palabras = [w for w in re.split(r'[\s¿\?,]+', m) if w]
            termino = ""
            if "llamada" in palabras:
                idx = palabras.index("llamada")
                if idx + 1 < len(palabras):
                    termino = palabras[idx + 1]
            elif "chavi" in palabras:
                termino = "chavi"
            else:
                for p in palabras:
                    if p not in ("existe", "una", "la", "el", "camara", "cámara", "cam", "llamada", "hay", "en", "de", "que", "busca", "buscar"):
                        termino = p
                        break
            return "camaras", {"tipo": "buscar", "termino": termino}

        # 7. Concepto de confianza
        if any(w in m for w in ("confianza", "confidence", "certeza")) and any(w in m for w in ("significa", "que es", "porcentaje", "78%", "50%", "umbral", "explica")):
            match_pct = re.search(r'(\d{1,3})\s*%', m)
            val = float(match_pct.group(1)) / 100.0 if match_pct else 0.78
            return "vision", {"tipo": "confianza_concepto", "valor": val}

        # 8. Eventos / Detecciones: "Último evento global"
        # Ej: "¿Qué detectó el último evento?", "ultimo evento", "última alerta", "que paso en el ultimo evento"
        if any(p in m for p in ("ultimo evento", "último evento", "ultima alerta", "última alerta", "el ultimo evento", "el último evento", "reciente evento")):
            # Verificar si menciona una cámara específica
            match_cam_especifica = re.search(r'(?:camara|cámara|cam)\s*([a-zA-Z0-9\-_]+)', m)
            if match_cam_especifica:
                return "eventos", {"tipo": "ultimo_evento_camara", "codigo": match_cam_especifica.group(1).upper()}
            return "eventos", {"tipo": "ultimo_evento_global"}

        # 9. Evento / Análisis por ID explícito
        match_evento_id = re.search(r'(?:evento|analisis|análisis|detecci[oó]n|alerta)\s*(?:#|id|num|número)?\s*(\d+)', m)
        if match_evento_id:
            return "eventos", {"tipo": "evento_id", "id": int(match_evento_id.group(1))}

        # 10. Consulta de evento por cámara específica
        match_camara = re.search(r'(?:camara|cámara|cam)\s*([a-zA-Z0-9\-_]+)', m)
        if match_camara and any(w in m for w in ("evento", "detecto", "paso", "alerta", "revisa")):
            return "eventos", {"tipo": "ultimo_evento_camara", "codigo": match_camara.group(1).upper()}

        # 11. Estadísticas y conteos temporales: "hoy", "ayer", "semana", "alertas pendientes"
        if any(w in m for w in ("cuantos", "cuántos", "cuantas", "cuántas", "total", "estadistica", "estadística", "promedio", "alertas", "eventos", "hubo", "detectaron")):
            if "semana anterior" in m or "semana pasada" in m or "semana previa" in m:
                return "estadisticas", {"periodo": "semana_anterior"}
            if "semana" in m:
                return "estadisticas", {"periodo": "esta_semana"}
            if "ayer" in m:
                return "estadisticas", {"periodo": "ayer"}
            if "pendiente" in m or "pendientes" in m:
                return "estadisticas", {"periodo": "pendientes"}
            if "top" in m or "mas detecciones" in m or "más detecciones" in m:
                return "estadisticas", {"periodo": "top_camaras"}
            if "hoy" in m or "dia" in m or "día" in m or "alertas" in m or "eventos" in m:
                return "estadisticas", {"periodo": "hoy"}

        # 12. Documentación autorizada de ARGOS / Athena
        terminos_doc = (
            "tripwire", "linea virtual", "línea virtual", "athena", "yolo", "mediapipe",
            "arquitectura", "flujo de deteccion", "flujo de detección", "salto", "agachado",
            "cruce", "biomecanica", "biomecánica", "evidencia", "rbac", "roles",
            "como funciona", "cómo funciona argos", "documentacion", "documentación"
        )
        if any(t in m for t in terminos_doc):
            return "documentacion", {}

        return "general", {}

    # ══════════════════════════════════════════════════════════════
    #  MANEJADORES POR MODO (FACTUALES Y OPTIMIZADOS)
    # ══════════════════════════════════════════════════════════════

    def _manejar_modo_eventos_y_vision(
        self, msg: str, meta: Dict[str, Any], usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        tipo_consulta = meta.get("tipo")
        herramientas: List[str] = []
        fuentes: List[FuenteAsistente] = []

        # 1. Concepto de confianza (Usa LLM para explicación pedagógica)
        if tipo_consulta == "confianza_concepto":
            etapas.append("consultando_metricas_confianza")
            t_d0 = time.perf_counter()
            val = meta.get("valor", 0.50)
            herramientas.append("explicar_concepto_de_confianza")
            info = explicar_concepto_de_confianza(val)
            tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

            fuentes.append(FuenteAsistente(
                tipo="sistema",
                referencia="sistema:metricas:confianza",
                titulo="Definición de Umbral y Confianza IA"
            ))

            etapas.append("generando_explicacion")
            t_llm0 = time.perf_counter()
            contexto_str = json.dumps(info, ensure_ascii=False, indent=2)
            prompt_sistema = f"{PROMPT_MODO_VISION}\n{construir_bloque_contexto('Métricas de Confianza', contexto_str)}"
            res_llm = self.ollama.chat([{"role": "user", "content": msg}], system_prompt=prompt_sistema)
            tiempos["generacion_llm_ms"] = round((time.perf_counter() - t_llm0) * 1000, 2)

            if res_llm.exito:
                contenido = res_llm.contenido
                generado_llm = True
            else:
                contenido = (
                    f"**{info['concepto']}**: En el sistema SiViA, un valor de confianza de **{info.get('valor_consultado')}%** "
                    f"representa la probabilidad matemática calculada por los modelos de visión artificial (YOLOv8 y MediaPipe).\n\n"
                    f"Interpretación: {info['interpretacion']}"
                )
                generado_llm = False

            etapas.append("preparando_respuesta")
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="info", severidad="normal", contenido=contenido,
                intent="vision_confianza", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="vision", modelo=res_llm.modelo_usado if res_llm.exito else None,
                fuentes=fuentes, herramientas=herramientas,
                generado_por_modelo=generado_llm, sin_datos=False,
                etapas=etapas, tiempos=tiempos
            )

        # 2. Verificación de permisos RBAC para eventos
        if not tiene_permiso(usuario, "eventos:ver"):
            etapas.append("verificacion_rbac_denegada")
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="denegado", severidad="warning",
                contenido=f"Tu rol `{rol}` no cuenta con el permiso `eventos:ver` necesario para consultar detalles de eventos o análisis.",
                intent="vision_evento", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="eventos", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        etapas.append("consultando_eventos")
        t_d0 = time.perf_counter()
        evento_data = None

        if tipo_consulta == "ultimo_evento_global":
            herramientas.append("obtener_ultimo_evento_global")
            evento_data = obtener_ultimo_evento_global(usuario)
            ref_str = f"evento:{evento_data['id']}" if evento_data else "evento:ultimo"
            titulo_fuente = "Último evento del sistema"

        elif tipo_consulta == "evento_id":
            eid = meta.get("id")
            herramientas.append(f"obtener_evento_por_id({eid})")
            evento_data = obtener_evento_por_id(eid, usuario)
            ref_str = f"evento:{eid}"
            titulo_fuente = f"Evento/Análisis #{eid}"

        elif tipo_consulta == "ultimo_evento_camara":
            cam = meta.get("codigo")
            herramientas.append(f"obtener_ultimo_evento_de_camara({cam})")
            evento_data = obtener_ultimo_evento_de_camara(cam, usuario)
            ref_str = f"camara:{cam}:ultimo_evento"
            titulo_fuente = f"Último evento en {cam}"

        tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

        # Si no hay evento registrado en la base de datos
        if not evento_data:
            id_buscado = meta.get("id") or meta.get("codigo") or "reciente"
            etapas.append("preparando_respuesta")
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="info", severidad="normal",
                contenido=f"No se encontró ningún registro de evento o análisis con el identificador `{id_buscado}` en la base de datos de ARGOS SiViA.",
                intent="vision_evento", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="vision", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        fuentes.append(FuenteAsistente(
            tipo="evento",
            referencia=ref_str,
            titulo=titulo_fuente,
            fecha_consulta=evento_data.get("detectado_en")
        ))

        # Respuesta factual por defecto
        contenido = (
            f"**Detalle del Evento #{evento_data['id']}** ({evento_data['tipo'].upper()}):\n\n"
            f"- **Cámara:** `{evento_data['camara_codigo']}` — {evento_data['estacion']}\n"
            f"- **Ubicación:** {evento_data['ubicacion']}\n"
            f"- **Detección:** {evento_data['tipo']} con **{evento_data['confianza_pct']}%** de confianza\n"
            f"- **Estado:** `{evento_data['estado']}`\n"
            f"- **Fecha y Hora:** {evento_data['detectado_en']}\n"
            f"- **Revisión:** {evento_data['revisado_en']}\n"
            f"- **Operador:** {evento_data['operador']}\n"
            f"- **Observaciones:** {evento_data['observaciones']}\n"
            f"- **Evidencia adjunta:** {'Disponible' if evento_data['tiene_evidencia'] else 'No registrada'}"
        )

        # Si el usuario solicita expresamente una explicación/análisis cualitativo (ej: "explícame el evento"),
        # usamos Qwen para la redacción sin tocar las cifras.
        requiere_explicacion = any(w in msg.lower() for w in ("explica", "explícame", "analiza", "interpretacion", "interpretación"))
        modelo_usado = None
        generado_llm = False

        if requiere_explicacion:
            etapas.append("generando_explicacion")
            t_llm0 = time.perf_counter()
            contexto_str = json.dumps(evento_data, ensure_ascii=False, indent=2)
            prompt_sistema = f"{PROMPT_MODO_VISION}\n{construir_bloque_contexto('Ficha de Detección de Visión Artificial', contexto_str)}"
            res_llm = self.ollama.chat([{"role": "user", "content": msg}], system_prompt=prompt_sistema)
            tiempos["generacion_llm_ms"] = round((time.perf_counter() - t_llm0) * 1000, 2)
            if res_llm.exito:
                contenido = res_llm.contenido
                modelo_usado = res_llm.modelo_usado
                generado_llm = True

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="vision_evento", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="vision", modelo=modelo_usado,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=generado_llm, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_camaras(
        self, msg: str, meta: Dict[str, Any], usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        etapas.append("consultando_camaras")
        t_d0 = time.perf_counter()
        herramientas: List[str] = []
        fuentes: List[FuenteAsistente] = []

        if not tiene_permiso(usuario, "camaras:ver"):
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="denegado", severidad="warning",
                contenido=f"Tu rol `{rol}` no cuenta con el permiso `camaras:ver` para consultar información del parque de cámaras.",
                intent="camaras", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="camaras", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        tipo_op = meta.get("tipo", "resumen")

        if tipo_op == "buscar":
            termino = meta.get("termino", "")
            herramientas.append(f"buscar_camaras('{termino}')")
            res_busqueda = buscar_camaras(termino, usuario)
            tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

            fuentes.append(FuenteAsistente(
                tipo="camaras",
                referencia=f"camaras:busqueda:{termino}",
                titulo=f"Búsqueda de cámaras: '{termino}'"
            ))

            encontradas = res_busqueda.get("encontradas", 0)
            if encontradas == 0:
                contenido = (
                    f"No existe ninguna cámara registrada con el nombre, código o estación `{termino}` en ARGOS SiViA.\n\n"
                    f"Puedes solicitar el resumen general de cámaras diciendo: *'¿Cuántas cámaras existen?'*."
                )
                sin_datos = True
            else:
                cams = res_busqueda.get("camaras", [])
                lineas_cams = [
                    f"- **`{c['codigo']}`** ({c['estacion']}): {c['ubicacion']} — Estado: `{c['estado']}` ({c['fps']} FPS, {c['resolucion']})"
                    for c in cams[:8]
                ]
                contenido = (
                    f"Se encontraron **{encontradas}** cámara(s) coincidentes con `{termino}`:\n\n"
                    + "\n".join(lineas_cams)
                )
                sin_datos = False

        else:
            # Resumen general de cámaras
            herramientas.append("obtener_resumen_camaras")
            res_cam = obtener_resumen_camaras(usuario)
            tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

            fuentes.append(FuenteAsistente(
                tipo="camaras",
                referencia="camaras:resumen",
                titulo="Inventario y Estado de Cámaras"
            ))

            cams_muestra = res_cam.get("camaras_muestra", [])
            lineas_muestra = [
                f"- `{c['codigo']}` ({c['estacion']}): `{c['estado']}`"
                for c in cams_muestra[:6]
            ]
            contenido = (
                f"**Inventario de Cámaras de ARGOS SiViA**:\n\n"
                f"- **Total registradas:** {res_cam['total']}\n"
                f"- **Activas (transmitiendo):** {res_cam['activas']}\n"
                f"- **Offline:** {res_cam['offline']}\n"
                f"- **En mantenimiento:** {res_cam['mantenimiento']}\n\n"
                f"**Muestra de cámaras:**\n" + "\n".join(lineas_muestra)
            )
            sin_datos = False

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="camaras", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="camaras", modelo=None,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=False, sin_datos=sin_datos,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_infraestructura(
        self, msg: str, meta: Dict[str, Any], usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        etapas.append("consultando_metricas_infraestructura")
        t_d0 = time.perf_counter()
        herramientas = ["obtener_metricas_infraestructura"]

        if not (tiene_permiso(usuario, "sistema:ver_metricas") or tiene_permiso(usuario, "sistema:ver_estado")):
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="denegado", severidad="warning",
                contenido=f"Tu rol `{rol}` no cuenta con el permiso `sistema:ver_metricas` para visualizar el estado del hardware e infraestructura.",
                intent="infraestructura", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="infraestructura", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        metricas = obtener_metricas_infraestructura(usuario)
        tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

        fuentes = [FuenteAsistente(
            tipo="infraestructura",
            referencia="sistema:metricas:hardware",
            titulo="Métricas de Hardware e Infraestructura",
            fecha_consulta=metricas.get("timestamp")
        )]

        cpu = metricas.get("cpu", {})
        ram = metricas.get("ram", {})
        disco = metricas.get("disco", {})
        red = metricas.get("red", {})
        uptime = metricas.get("uptime", "N/A")

        contenido = (
            f"**Estado de Infraestructura y Servidor** (Zona: America/Bogota):\n\n"
            f"- **Uptime:** {uptime}\n"
            f"- **CPU:** {cpu.get('uso_pct', 'N/A')}% (Núcleos: {cpu.get('nucleos', 'N/A')}, Hilos: {cpu.get('hilos', 'N/A')})\n"
            f"- **Memoria RAM:** {ram.get('uso_pct', 'N/A')}% (Usado: {ram.get('usado_gb', 'N/A')} GB / Total: {ram.get('total_gb', 'N/A')} GB)\n"
            f"- **Disco Almacenamiento:** {disco.get('uso_pct', 'N/A')}% (Libre: {disco.get('libre_gb', 'N/A')} GB / Total: {disco.get('total_gb', 'N/A')} GB)\n"
            f"- **Red I/O:** Recibidos: {red.get('bytes_recibidos_mb', 'N/A')} MB | Enviados: {red.get('bytes_enviados_mb', 'N/A')} MB\n"
            f"- **Conexiones activas:** {red.get('conexiones_activas', 'N/A')}"
        )

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad=snapshot.nivel, contenido=contenido,
            intent="infraestructura", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="infraestructura", modelo=None,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=False, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_usuarios(
        self, msg: str, meta: Dict[str, Any], usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        etapas.append("consultando_usuarios")
        t_d0 = time.perf_counter()
        herramientas = ["obtener_usuarios_resumen"]

        if not tiene_permiso(usuario, "usuarios:ver"):
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="denegado", severidad="warning",
                contenido=f"Tu rol `{rol}` no cuenta con el permiso `usuarios:ver` para consultar la gestión de usuarios del sistema.",
                intent="usuarios", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="usuarios", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        usr_data = obtener_usuarios_resumen(usuario)
        tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

        fuentes = [FuenteAsistente(
            tipo="usuarios",
            referencia="usuarios:resumen",
            titulo="Gestión de Usuarios y Roles"
        )]

        roles_str = ", ".join([f"{r}: {c}" for r, c in usr_data.get("por_rol", {}).items()])
        muestra_str = "\n".join([
            f"- `{u['username']}` ({u['nombre']}) — Rol: `{u['rol']}`"
            for u in usr_data.get("usuarios_activos_muestra", [])[:6]
        ])

        contenido = (
            f"**Resumen de Usuarios en ARGOS SiViA**:\n\n"
            f"- **Total usuarios:** {usr_data['total']}\n"
            f"- **Activos:** {usr_data['activos']} | **Inactivos:** {usr_data['inactivos']}\n"
            f"- **Distribución por rol:** {roles_str}\n\n"
            f"**Usuarios activos:**\n{muestra_str}"
        )

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="usuarios", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="usuarios", modelo=None,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=False, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_auditoria(
        self, msg: str, meta: Dict[str, Any], usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        etapas.append("consultando_auditoria")
        t_d0 = time.perf_counter()
        herramientas = ["obtener_actividad_auditoria"]

        if not tiene_permiso(usuario, "auditoria:ver"):
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="denegado", severidad="warning",
                contenido=f"Tu rol `{rol}` no cuenta con el permiso `auditoria:ver` para consultar la bitácora de auditoría.",
                intent="auditoria", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="auditoria", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        aud_data = obtener_actividad_auditoria(usuario, limite=5)
        tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

        fuentes = [FuenteAsistente(
            tipo="auditoria",
            referencia="auditoria:ultimas_acciones",
            titulo="Bitácora de Auditoría"
        )]

        regs = aud_data.get("registros", [])
        if not regs:
            contenido = "No hay registros recientes en la bitácora de auditoría del sistema."
        else:
            lineas = [
                f"- **[{r['fecha']}]** `{r['usuario']}` ({r['rol']}): {r['accion']} — {r['detalle'] or 'Sin detalles'}"
                for r in regs
            ]
            contenido = "**Actividad Reciente de Auditoría**:\n\n" + "\n".join(lineas)

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="auditoria", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="auditoria", modelo=None,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=False, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_estadisticas(
        self, msg: str, meta: Dict[str, Any], usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        periodo = meta.get("periodo", "hoy")
        herramientas = [f"consultar_estadisticas_eventos('{periodo}')"]

        if not (tiene_permiso(usuario, "estadisticas:ver") or tiene_permiso(usuario, "eventos:ver")):
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="denegado", severidad="warning",
                contenido=f"Tu rol `{rol}` no tiene permiso para consultar estadísticas o métricas del sistema.",
                intent="estadisticas", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="estadisticas", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        etapas.append("consultando_estadisticas")
        t_d0 = time.perf_counter()
        stats_data = consultar_estadisticas_eventos(periodo, usuario)
        tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

        if not stats_data:
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="info", severidad="normal",
                contenido="No se pudieron calcular estadísticas para el intervalo seleccionado.",
                intent="estadisticas", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="estadisticas", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        fuentes = [FuenteAsistente(
            tipo="estadistica",
            referencia=f"stats:eventos:{periodo}",
            titulo=f"Estadísticas de Eventos ({stats_data.get('descripcion', periodo)})",
            fecha_consulta=stats_data.get("calculado_en") or stats_data.get("fecha_consulta")
        )]

        # RESPUESTA FACTUAL DIRECTA (Garantiza cifras 100% exactas sin reformulación LLM)
        if periodo == "pendientes":
            top_cam = ", ".join([f"{c['camara']} ({c['total']})" for c in stats_data.get("camaras_con_mas_pendientes", [])]) or "Ninguna"
            contenido = (
                f"**Alertas Pendientes de Revisión** (Zona America/Bogota):\n\n"
                f"- **Total pendientes:** {stats_data['total_pendientes']}\n"
                f"- **Cámaras con más pendientes:** {top_cam}\n\n"
                f"*(Datos oficiales en tiempo real de la base de datos)*"
            )
        elif periodo == "top_camaras":
            lineas = [f"- **{c['camara']}** ({c['estacion']}): {c['eventos']} eventos" for c in stats_data.get("ranking", [])]
            contenido = (
                f"**Cámaras con mayor número de detecciones** (Últimos 7 días):\n\n"
                + "\n".join(lineas)
            )
        else:
            contenido = (
                f"**Estadísticas de {stats_data.get('descripcion', periodo)}** (Zona: America/Bogota):\n\n"
                f"- **Total de eventos detectados:** {stats_data.get('total_eventos', 0)}\n"
                f"- **Confirmados por operador:** {stats_data.get('confirmados', 0)}\n"
                f"- **Descartados:** {stats_data.get('descartados', 0)}\n"
                f"- **Pendientes de revisión:** {stats_data.get('pendientes', 0)}\n\n"
                f"*(Datos verificados de base de datos; cifras exactas no aproximadas)*"
            )

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="estadisticas", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="estadisticas", modelo=None,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=False, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_documentacion(
        self, msg: str, usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        etapas.append("buscando_documentacion")
        t_d0 = time.perf_counter()
        herramientas = ["recuperar_documentacion"]
        secciones = recuperar_documentacion(msg, top_k=2)
        tiempos["consulta_datos_ms"] = round((time.perf_counter() - t_d0) * 1000, 2)

        if not secciones:
            tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            return self._armar_respuesta(
                tipo="info", severidad="normal",
                contenido="No se encontró documentación autorizada suficiente en la base de conocimiento local para responder esta pregunta específica.",
                intent="documentacion", rol=rol, snapshot=snapshot,
                session_key=session_key, msg_user=msg,
                modo="documentacion", herramientas=herramientas, sin_datos=True,
                etapas=etapas, tiempos=tiempos
            )

        fuentes = [
            FuenteAsistente(
                tipo="documentacion",
                referencia=f"docs:{sec.documento}#{sec.titulo.lower().replace(' ', '-')}",
                titulo=f"{sec.documento}: {sec.titulo}"
            )
            for sec in secciones
        ]

        textos_doc = "\n\n".join([f"### [{sec.documento}] {sec.titulo}\n{sec.contenido}" for sec in secciones])

        etapas.append("generando_explicacion")
        t_llm0 = time.perf_counter()
        prompt_sistema = f"{PROMPT_MODO_DOCUMENTACION}\n{construir_bloque_contexto('Documentación Oficial de ARGOS SiViA', textos_doc)}"
        res_llm = self.ollama.chat([{"role": "user", "content": msg}], system_prompt=prompt_sistema)
        tiempos["generacion_llm_ms"] = round((time.perf_counter() - t_llm0) * 1000, 2)

        if res_llm.exito:
            contenido = res_llm.contenido
            generado_llm = True
        else:
            contenido = f"**Documentación Oficial de ARGOS SiViA:**\n\n{textos_doc[:600]}..."
            generado_llm = False

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="documentacion", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="documentacion", modelo=res_llm.modelo_usado if res_llm.exito else None,
            fuentes=fuentes, herramientas=herramientas,
            generado_por_modelo=generado_llm, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_ayuda(
        self, msg: str, usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        fuentes = [FuenteAsistente(
            tipo="ayuda",
            referencia="sistema:ayuda",
            titulo="Capacidades y Permisos de Hermes"
        )]

        permisos_texto = []
        if tiene_permiso(usuario, "eventos:ver"):
            permisos_texto.append("- **Eventos:** Consulta de último evento global, eventos por ID y análisis por cámara.")
        if tiene_permiso(usuario, "camaras:ver"):
            permisos_texto.append("- **Cámaras:** Búsqueda específica por nombre/código/estación y resumen de estado del parque.")
        if tiene_permiso(usuario, "estadisticas:ver") or tiene_permiso(usuario, "eventos:ver"):
            permisos_texto.append("- **Estadísticas:** Conteo de eventos de hoy, ayer, semana y alertas pendientes en Bogota TZ.")
        if tiene_permiso(usuario, "sistema:ver_metricas") or tiene_permiso(usuario, "sistema:ver_estado"):
            permisos_texto.append("- **Infraestructura:** Monitoreo en tiempo real de CPU, RAM, disco, red y uptime.")
        if tiene_permiso(usuario, "usuarios:ver"):
            permisos_texto.append("- **Usuarios:** Consulta de usuarios activos y distribución por roles.")
        if tiene_permiso(usuario, "auditoria:ver"):
            permisos_texto.append("- **Auditoría:** Registro de actividades y bitácora del sistema.")
        permisos_texto.append("- **Conceptos y Docs:** Explicaciones de tripwire, biomecánica, YOLOv8, MediaPipe y confianza IA.")

        contenido = (
            f"**Hermes IA — Asistente Operativo de ARGOS SiViA**\n\n"
            f"Tu rol actual es `{rol}`. De acuerdo con tus permisos asignados, puedo asistirte en:\n\n"
            + "\n".join(permisos_texto)
        )

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="ayuda", severidad="normal", contenido=contenido,
            intent="ayuda", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="ayuda", fuentes=fuentes, herramientas=["verificar_permisos_rol"],
            generado_por_modelo=False, sin_datos=False,
            etapas=etapas, tiempos=tiempos
        )

    def _manejar_modo_general(
        self, msg: str, usuario: dict, rol: str,
        session_key: str, snapshot: SystemHealthSnapshot,
        etapas: List[str], tiempos: Dict[str, float], t0: float
    ) -> HermesResponse:
        etapas.append("generando_explicacion")
        t_llm0 = time.perf_counter()
        historial_llm = session_cache.get_messages_for_llm(session_key)
        historial_llm.append({"role": "user", "content": msg})

        res_llm = self.ollama.chat(historial_llm, system_prompt=PROMPT_MODO_GENERAL)
        tiempos["generacion_llm_ms"] = round((time.perf_counter() - t_llm0) * 1000, 2)

        advertencias = []
        if res_llm.exito:
            contenido = res_llm.contenido
            generado_llm = True
        else:
            contenido = (
                "Hermes IA (Modo General): El modelo local Qwen 2.5 no se encuentra disponible "
                "(verifica que Ollama esté ejecutándose en http://127.0.0.1:11434).\n\n"
                "Para consultas operativas del sistema ARGOS SiViA (cámaras, eventos, infraestructura o alertas), "
                "puedes realizar tu consulta directamente."
            )
            advertencias.append("Ollama local desconectado o no responde")
            generado_llm = False

        etapas.append("preparando_respuesta")
        tiempos["total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return self._armar_respuesta(
            tipo="info", severidad="normal", contenido=contenido,
            intent="conversacion_general", rol=rol, snapshot=snapshot,
            session_key=session_key, msg_user=msg,
            modo="general", modelo=res_llm.modelo_usado if res_llm.exito else None,
            fuentes=[], herramientas=[], generado_por_modelo=generado_llm,
            sin_datos=not res_llm.exito, advertencias=advertencias,
            etapas=etapas, tiempos=tiempos
        )

    # ══════════════════════════════════════════════════════════════
    #  CONSTRUCTOR DE RESPUESTA HOMOGÉNEA
    # ══════════════════════════════════════════════════════════════

    def _armar_respuesta(
        self, tipo: str, severidad: str, contenido: str,
        intent: str, rol: str, snapshot: SystemHealthSnapshot,
        session_key: str, msg_user: str,
        modo: str, modelo: Optional[str] = None,
        fuentes: Optional[List[FuenteAsistente]] = None,
        herramientas: Optional[List[str]] = None,
        generado_por_modelo: bool = False,
        sin_datos: bool = False,
        advertencias: Optional[List[str]] = None,
        etapas: Optional[List[str]] = None,
        tiempos: Optional[Dict[str, float]] = None,
    ) -> HermesResponse:
        # Registrar turno en RAM
        session_cache.add_turn(session_key, rol, msg_user, contenido)

        from services.hermes_service import _acciones_por_rol
        acciones = _acciones_por_rol(rol, intent)

        sugerencias = [
            "¿Qué detectó el último evento?",
            "¿Cuántas alertas hay hoy?",
            "¿Existe una cámara llamada Chavi?",
            "¿Cuál es el estado de CPU, RAM y disco?",
        ]

        log.info(
            "Hermes query procesada: modo=%s intent=%s herramientas=%s latencia_total_ms=%.2f",
            modo, intent, herramientas or [], (tiempos or {}).get("total_ms", 0.0)
        )

        return HermesResponse(
            tipo=tipo,
            severidad=severidad,
            contenido=contenido,
            alertas_resumen=[],
            acciones=acciones,
            sugerencias=sugerencias,
            estado_sistema=snapshot,
            intencion_detectada=intent,
            rol_usuario=rol,
            modo=modo,
            modelo=modelo,
            fuentes=fuentes or [],
            herramientas_usadas=herramientas or [],
            respuesta_generada_por_modelo=generado_por_modelo,
            sin_datos=sin_datos,
            advertencias=advertencias or [],
            etapas_procesamiento=etapas or [],
            tiempos_ms=tiempos or {}
        )


assistant_orchestrator = AssistantOrchestrator()
