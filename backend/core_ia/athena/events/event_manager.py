# events/event_manager.py
# Actualizado: mapeo estricto de EVENTS + dispatch hacia SSE y auditoría Web.

import time
import logging

logger = logging.getLogger(__name__)

# ── Catálogo canónico de eventos detectados por Athena ───────────────────────
EVENTS = {
    "PERSONA_DETECTADA": "persona",
    "BRAZO_ARRIBA":      "brazo",
    "MANO_ABIERTA":      "mano_abierta",
    "MANO_CERRADA":      "mano_cerrada",
    "TARJETA_VALIDA":    "tarjeta_valida",
    "TARJETA_INVALIDA":  "tarjeta_invalida",
    "ACCESO_CONCEDIDO":  "acceso",
    "POSE_ANOMALA":      "pose_anomala",
}


class EventManager:
    """
    Gestiona la detección de transiciones de estado (edge-detection)
    y despacha los eventos resultantes a:
      1. Log de consola
      2. Base de datos principal (auditoría/eventos) a través del
         módulo de persistencia del ecosistema Web (db.guardar_evento).
    
    NOTA: Las notificaciones visuales en tiempo real se envían mediante
    el AthenaThread directamente a la cola SSE de AthenaManager,
    exclusivamente a la vista "Cámaras" — sin spam global.
    """

    def __init__(self):
        self.prev_states = {
            "persona": False,
            "brazo":   False,
            "mano":    "",
            "tarjeta": False,
        }
        self.last_event_time = {
            "acceso": 0.0
        }
        self.cooldown = 3  # segundos entre eventos de acceso

    # ── Mapeo de estado interno → clave EVENTS ───────────────────────────────
    @staticmethod
    def _get_event_key(tipo_interno: str) -> str:
        """Devuelve la clave canónica del catálogo EVENTS dado un tipo interno."""
        _map = {
            "persona":        "PERSONA_DETECTADA",
            "brazo":          "BRAZO_ARRIBA",
            "mano_abierta":   "MANO_ABIERTA",
            "mano_cerrada":   "MANO_CERRADA",
            "tarjeta":        "TARJETA_VALIDA",
            "tarjeta_invalida": "TARJETA_INVALIDA",
            "acceso":         "ACCESO_CONCEDIDO",
            "pose_anomala":   "POSE_ANOMALA",
        }
        return _map.get(tipo_interno, tipo_interno.upper())

    def procesar_eventos(self, estado):
        """
        Detecta transiciones de estado (edge detection) y devuelve
        lista de tuplas (tipo_interno, descripcion_legible).
        """
        eventos = []

        # PERSONA
        if estado["persona"] and not self.prev_states["persona"]:
            eventos.append(("persona", "Persona detectada"))

        # BRAZO
        if estado["brazo"] and not self.prev_states["brazo"]:
            eventos.append(("brazo", "Brazo levantado"))

        # MANO (transición de estado)
        if estado["mano"] != "" and estado["mano"] != self.prev_states["mano"]:
            if estado["mano"] == "cerrada":
                eventos.append(("mano_cerrada", "Mano cerrada"))
            elif estado["mano"] == "abierta":
                eventos.append(("mano_abierta", "Mano abierta"))

        # TARJETA
        if estado["tarjeta"] and not self.prev_states["tarjeta"]:
            eventos.append(("tarjeta", "Tarjeta válida detectada"))

        # Actualizar estados anteriores
        self.prev_states = dict(estado)
        return eventos

    def procesar_evento_decision(self, evento):
        """
        Eventos complejos (acceso) con cooldown para evitar spam.
        """
        eventos = []
        ahora = time.time()

        if evento == "acceso":
            if ahora - self.last_event_time["acceso"] > self.cooldown:
                eventos.append(("acceso", "Acceso biométrico concedido"))
                self.last_event_time["acceso"] = ahora

        return eventos

    def dispatch(self, eventos):
        """
        Ejecuta los eventos detectados:
        - Log en consola con clave canónica EVENTS
        - Persistencia en BD base (ignorar si módulo no disponible, p.ej. modo standalone)
        """
        _guardar = None
        try:
            from database.db import guardar_evento
            _guardar = guardar_evento
        except ImportError:
            pass  # Modo standalone sin BD web

        for tipo_interno, descripcion in eventos:
            clave = self._get_event_key(tipo_interno)
            tipo_canonico = EVENTS.get(clave, tipo_interno)
            logger.info(f"[ATHENA] {clave} → {descripcion}")
            print(f"[ATHENA] {clave} ({tipo_canonico}) → {descripcion}")

            if _guardar:
                try:
                    _guardar(tipo_canonico, descripcion)
                except Exception as e:
                    logger.warning(f"No se pudo persistir evento '{clave}': {e}")