"""
services/ollama_service.py
────────────────────────────────────────────────────────────
Cliente HTTP local para interactuar con Ollama (Qwen 2.5 3B).

REGLAS DE SEGURIDAD:
- Conexión exclusivamente local por loopback (127.0.0.1).
- No transmite datos al exterior, internet ni APIs de terceros.
- Timeout estricto y captura limpia de errores (Ollama apagado, timeout, etc.).
- Nunca registra tokens, credenciales ni prompts sensibles en logs.
"""

from __future__ import annotations
import os
import time
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

try:
    import httpx
    HTTP_CLIENT = "httpx"
except ImportError:
    import urllib.request
    import urllib.error
    HTTP_CLIENT = "urllib"

log = logging.getLogger("ARGOS.OllamaService")

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_TIMEOUT = 60
DEFAULT_MAX_CONTEXT_CHARS = 8000


@dataclass
class OllamaChatResult:
    exito: bool
    contenido: str
    error: Optional[str] = None
    modelo_usado: str = ""
    duracion_ms: int = 0


class OllamaClient:
    """Cliente para el endpoint /api/chat de Ollama local."""

    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.configured_model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        try:
            self.timeout = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT))
        except (ValueError, TypeError):
            self.timeout = DEFAULT_TIMEOUT

        try:
            self.max_context_chars = int(os.environ.get("OLLAMA_MAX_CONTEXT_CHARS", DEFAULT_MAX_CONTEXT_CHARS))
        except (ValueError, TypeError):
            self.max_context_chars = DEFAULT_MAX_CONTEXT_CHARS

        self._active_model_cache: Optional[str] = None

    def health_check(self) -> Dict[str, Any]:
        """
        Verifica si Ollama está en ejecución y qué modelos tiene descargados.
        GET /api/tags
        """
        url = f"{self.base_url}/api/tags"
        try:
            if HTTP_CLIENT == "httpx":
                with httpx.Client(timeout=3.0) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        modelos = [m.get("name", "") for m in data.get("models", [])]
                        return {
                            "disponible": True,
                            "modelos": modelos,
                            "modelo_configurado": self.configured_model,
                        }
            else:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        modelos = [m.get("name", "") for m in data.get("models", [])]
                        return {
                            "disponible": True,
                            "modelos": modelos,
                            "modelo_configurado": self.configured_model,
                        }
        except Exception as e:
            return {
                "disponible": False,
                "modelos": [],
                "modelo_configurado": self.configured_model,
                "error": str(e)
            }

        return {"disponible": False, "modelos": [], "modelo_configurado": self.configured_model}

    def _resolver_modelo(self) -> str:
        """
        Resuelve el tag exacto disponible (ej. si está 'qwen2.5:3b-instruct' y configurado 'qwen2.5:3b').
        """
        if self._active_model_cache:
            return self._active_model_cache

        estado = self.health_check()
        disponibles = estado.get("modelos", [])
        if not disponibles:
            return self.configured_model

        if self.configured_model in disponibles:
            self._active_model_cache = self.configured_model
            return self.configured_model

        # Buscar coincidencia aproximada
        for m in disponibles:
            if m.startswith(self.configured_model) or self.configured_model.split(":")[0] in m:
                self._active_model_cache = m
                return m

        self._active_model_cache = disponibles[0]
        return self._active_model_cache

    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> OllamaChatResult:
        """
        Envía una solicitud al endpoint POST /api/chat de Ollama.
        """
        start_time = time.time()
        modelo = self._resolver_modelo()
        url = f"{self.base_url}/api/chat"

        payload_messages: List[Dict[str, str]] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})

        # Limitar longitud total de mensajes para no exceder contexto
        chars_acumulados = 0
        for msg in reversed(messages):
            content = msg.get("content", "")
            chars_acumulados += len(content)
            if chars_acumulados > self.max_context_chars:
                break
            payload_messages.insert(1 if system_prompt else 0, msg)

        body = {
            "model": modelo,
            "messages": payload_messages,
            "stream": False,
            "options": {
                "temperature": 0.2,  # Respuesta precisa y controlada
                "top_p": 0.9,
            }
        }

        try:
            if HTTP_CLIENT == "httpx":
                with httpx.Client(timeout=float(self.timeout)) as client:
                    resp = client.post(url, json=body)
                    duracion_ms = int((time.time() - start_time) * 1000)

                    if resp.status_code != 200:
                        log.warning(f"Ollama respondió HTTP {resp.status_code}")
                        return OllamaChatResult(
                            exito=False,
                            contenido="",
                            error=f"Error en servidor Ollama (HTTP {resp.status_code})",
                            modelo_usado=modelo,
                            duracion_ms=duracion_ms,
                        )

                    data = resp.json()
            else:
                data_bytes = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=float(self.timeout)) as resp:
                    duracion_ms = int((time.time() - start_time) * 1000)
                    if resp.status != 200:
                        return OllamaChatResult(
                            exito=False,
                            contenido="",
                            error=f"Error en servidor Ollama (HTTP {resp.status})",
                            modelo_usado=modelo,
                            duracion_ms=duracion_ms,
                        )
                    data = json.loads(resp.read().decode("utf-8"))

            content = data.get("message", {}).get("content", "").strip()
            if not content:
                return OllamaChatResult(
                    exito=False,
                    contenido="",
                    error="Respuesta vacía generada por el modelo",
                    modelo_usado=modelo,
                    duracion_ms=duracion_ms,
                )

            return OllamaChatResult(
                exito=True,
                contenido=content,
                modelo_usado=modelo,
                duracion_ms=duracion_ms,
            )

        except Exception as e:
            duracion_ms = int((time.time() - start_time) * 1000)
            err_msg = str(e)
            if "ConnectionRefused" in err_msg or "WinError 10061" in err_msg or "ConnectError" in type(e).__name__:
                log.info("Ollama no está disponible (conexión rechazada en 127.0.0.1:11434)")
                return OllamaChatResult(
                    exito=False,
                    contenido="",
                    error="Ollama local no está disponible o está apagado",
                    modelo_usado=modelo,
                    duracion_ms=duracion_ms,
                )
            if "Timeout" in type(e).__name__ or "timeout" in err_msg.lower():
                log.warning("Timeout al comunicarse con Ollama local")
                return OllamaChatResult(
                    exito=False,
                    contenido="",
                    error="Tiempo de espera agotado al consultar Ollama",
                    modelo_usado=modelo,
                    duracion_ms=duracion_ms,
                )

            log.warning(f"Error comunicando con Ollama: {type(e).__name__}")
            return OllamaChatResult(
                exito=False,
                contenido="",
                error=f"Fallo de comunicación con el modelo local: {type(e).__name__}",
                modelo_usado=modelo,
                duracion_ms=duracion_ms,
            )


# Singleton
ollama_client = OllamaClient()
