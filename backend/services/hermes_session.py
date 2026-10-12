"""
services/hermes_session.py
────────────────────────────────────────────────────────────
ARGOS - SiViA  ·  Hermes IA - Caché de Sesión Segura en RAM

REGLAS DE SEGURIDAD:
- Almacena el historial breve EN MEMORIA RAM exclusivamente.
- NUNCA almacena el X-Token en texto plano como clave de sesión.
- Las sesiones se aíslan por usuario_id mediante un hash SHA-256 irreversible.
- Dos usuarios NUNCA comparten historial aunque envíen el mismo session_id.
- Máximo MAX_TURNS turnos (por defecto 6-8).
- Expiración automática tras 30 minutos de inactividad.
"""

from __future__ import annotations
import os
import hashlib
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional

log = logging.getLogger("ARGOS.Session")

try:
    MAX_TURNS = int(os.environ.get("OLLAMA_MAX_HISTORY_TURNS", "6"))
except (ValueError, TypeError):
    MAX_TURNS = 6

EXPIRY_MINS = 30


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
    __slots__ = ("turns", "last_access")

    def __init__(self):
        self.turns:       list[Turn] = []
        self.last_access: datetime   = datetime.now()

    def add(self, role: str, user_msg: str, bot_msg: str) -> None:
        self.turns.append(Turn(role, user_msg, bot_msg))
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]
        self.last_access = datetime.now()

    def is_expired(self) -> bool:
        return datetime.now() - self.last_access > timedelta(minutes=EXPIRY_MINS)

    def get_context(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.turns]


class SessionCache:
    """
    Almacén de sesiones en RAM thread-safe con claves hasheadas de usuario.
    """

    def __init__(self):
        self._store: dict[str, _SessionEntry] = {}
        self._lock  = threading.RLock()

    @staticmethod
    def derive_key(user_id: int | str, session_id: Optional[str] = None, token: Optional[str] = None) -> str:
        """
        Deriva un hash criptográfico SHA-256 único por usuario.
        Nunca expone el token en texto claro ni permite colisión entre usuarios.
        """
        uid = str(user_id) if user_id is not None else "anon"
        sid = str(session_id).strip() if session_id else "default"
        # Usar sólo una firma derivada si hay token
        tok_signature = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16] if token else "no_tok"
        semilla = f"usr:{uid}|sid:{sid}|sig:{tok_signature}"
        return hashlib.sha256(semilla.encode("utf-8")).hexdigest()

    def add_turn(self, session_key: str, rol: str, user_msg: str, bot_msg: str) -> None:
        if not session_key:
            return
        with self._lock:
            if session_key not in self._store:
                self._store[session_key] = _SessionEntry()
            self._store[session_key].add(rol, user_msg, bot_msg)

    def get_history(self, session_key: str) -> list[dict[str, Any]]:
        if not session_key:
            return []
        with self._lock:
            entry = self._store.get(session_key)
            if not entry:
                return []
            if entry.is_expired():
                del self._store[session_key]
                return []
            entry.last_access = datetime.now()
            return entry.get_context()

    def get_messages_for_llm(self, session_key: str) -> List[Dict[str, str]]:
        """
        Devuelve el historial en formato de lista de mensajes Ollama [{"role": "user"|"assistant", "content": "..."}].
        """
        history = self.get_history(session_key)
        messages: List[Dict[str, str]] = []
        for t in history:
            u = t.get("usuario")
            b = t.get("hermes")
            if u:
                messages.append({"role": "user", "content": u})
            if b:
                messages.append({"role": "assistant", "content": b})
        return messages

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired()]
            for k in expired:
                del self._store[k]
            return len(expired)


session_cache = SessionCache()
