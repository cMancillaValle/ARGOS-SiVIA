"""
services/hermes_session.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Hermes IA - Caché de Sesión Volátil

Almacena el historial breve de conversación EN MEMORIA RAM.
NO usa SQLite ni ningún archivo persistente.
El historial se pierde al reiniciar el servidor (comportamiento deseado).

Política de retención:
  - Máximo 8 turnos por sesión (configurable con MAX_TURNS)
  - Expiración: 30 minutos de inactividad
  - El cleanup se llama automáticamente en cada request

Uso:
    from services.hermes_session import session_cache

    session_cache.add_turn(token, rol, msg_user, msg_bot)
    history = session_cache.get_history(token)  # list[dict]
    session_cache.cleanup_expired()
"""

from __future__ import annotations
import logging
import threading
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger("ARGOS.Session")

MAX_TURNS   = 8         # turnos máximos por sesión
EXPIRY_MINS = 30        # minutos de inactividad antes de expirar


class Turn:
    """Representa un único turno de conversación (user → bot)."""
    __slots__ = ("role", "user_msg", "bot_msg", "ts")

    def __init__(self, role: str, user_msg: str, bot_msg: str):
        self.role     = role
        self.user_msg = user_msg
        self.bot_msg  = bot_msg
        self.ts       = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rol":      self.role,
            "usuario":  self.user_msg,
            "hermes":   self.bot_msg,
            "hora":     self.ts.strftime("%H:%M"),
        }


class _SessionEntry:
    """Una sesión individual con su historial y timestamp de último acceso."""
    __slots__ = ("turns", "last_access")

    def __init__(self):
        self.turns:       list[Turn] = []
        self.last_access: datetime   = datetime.now()

    def add(self, role: str, user_msg: str, bot_msg: str) -> None:
        self.turns.append(Turn(role, user_msg, bot_msg))
        # Mantener solo los últimos MAX_TURNS turnos
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]
        self.last_access = datetime.now()

    def is_expired(self) -> bool:
        return datetime.now() - self.last_access > timedelta(minutes=EXPIRY_MINS)

    def get_context(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.turns]


class SessionCache:
    """
    Almacén central de sesiones en RAM.

    Es thread-safe gracias a un RLock.
    La clave es el token de autenticación del usuario (X-Token),
    que ya es único por sesión en el sistema existente.
    """

    def __init__(self):
        self._store: dict[str, _SessionEntry] = {}
        self._lock  = threading.RLock()

    # ── API pública ─────────────────────────────────────────

    def add_turn(self, token: str, rol: str, user_msg: str, bot_msg: str) -> None:
        """Registra un turno de conversación para el token dado."""
        if not token:
            return
        with self._lock:
            if token not in self._store:
                self._store[token] = _SessionEntry()
            self._store[token].add(rol, user_msg, bot_msg)

    def get_history(self, token: str) -> list[dict[str, Any]]:
        """Devuelve el historial de la sesión como lista de dicts."""
        if not token:
            return []
        with self._lock:
            entry = self._store.get(token)
            if entry is None or entry.is_expired():
                return []
            return entry.get_context()

    def get_last_intent(self, token: str) -> str | None:
        """
        Devuelve la última intención del bot para contexto de seguimiento.
        Útil para resolver pronombres ("¿y esas?", "¿cuántas hay?").
        """
        history = self.get_history(token)
        if not history:
            return None
        last = history[-1]
        # El campo 'intent' se guarda opcionalmente en bot_msg como metadata
        return last.get("intent_detectado")

    def cleanup_expired(self) -> int:
        """
        Elimina sesiones expiradas. Devuelve el número de sesiones purgadas.
        Llamar en cada request para evitar acumulación de memoria.
        """
        expired_keys = []
        with self._lock:
            for token, entry in self._store.items():
                if entry.is_expired():
                    expired_keys.append(token)
            for key in expired_keys:
                del self._store[key]
        if expired_keys:
            log.info(f"SessionCache: {len(expired_keys)} sesión(es) expirada(s) purgada(s).")
        return len(expired_keys)

    def count_active(self) -> int:
        """Devuelve el número de sesiones activas (sin limpiar)."""
        with self._lock:
            return len(self._store)

    def clear_session(self, token: str) -> None:
        """Limpia manualmente la sesión de un token específico (logout)."""
        with self._lock:
            self._store.pop(token, None)


# ── Instancia singleton global ───────────────────────────────
# Importar desde aquí: from services.hermes_session import session_cache
session_cache = SessionCache()
