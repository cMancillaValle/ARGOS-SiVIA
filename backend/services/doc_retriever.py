"""
services/doc_retriever.py
────────────────────────────────────────────────────────────
Recuperador local determinista de documentación autorizada de ARGOS - SiViA.

Carga y busca fragmentos en archivos Markdown bajo backend/data/docs/.
Diseñado sin dependencias pesadas (sin Chroma, sin LangChain, sin embeddings remotos).
Puede sustituirse a futuro por RAG local conservando la misma interfaz.
"""

from __future__ import annotations
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import List

DOCS_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "docs"
))

STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "en",
    "a", "por", "para", "con", "sin", "sobre", "entre", "es", "son", "que", "como",
    "del", "al", "se", "su", "sus", "lo", "mi", "tu", "te", "me", "nos", "este",
    "esta", "estos", "estas", "cual", "cuales", "donde", "cuando", "quien", "argos",
    "sivia", "sistema", "explicame", "que", "dime", "cual", "cuentame"
}


@dataclass
class DocSection:
    documento: str      # Nombre del archivo, ej: "arquitectura.md"
    titulo: str         # Título de la sección, ej: "Componentes Principales"
    contenido: str      # Texto en Markdown
    score: float = 0.0  # Puntuación de relevancia


def _normalize(text: str) -> str:
    """Normaliza quitando acentos y caracteres especiales."""
    nfkd = unicodedata.normalize('NFKD', text.lower())
    sin_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r'[^a-z0-9\s]', ' ', sin_acento)


def _tokenize(text: str) -> set[str]:
    """Extrae palabras clave significativas."""
    words = _normalize(text).split()
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def cargar_secciones_autorizadas() -> List[DocSection]:
    """Lee y particiona los archivos .md autorizados del directorio local."""
    if not os.path.isdir(DOCS_DIR):
        return []

    secciones: List[DocSection] = []
    archivos = sorted([f for f in os.listdir(DOCS_DIR) if f.endswith(".md") and f != "README.md"])

    for filename in archivos:
        path = os.path.join(DOCS_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except Exception:
            continue

        # Particionar por encabezados de nivel 1 o 2
        bloques = re.split(r'\n(?=#{1,2}\s+)', raw_text)
        for bloque in bloques:
            bloque = bloque.strip()
            if not bloque:
                continue

            # Extraer primer encabezado como título
            lineas = bloque.splitlines()
            primera = lineas[0].strip() if lineas else ""
            if primera.startswith("#"):
                titulo = re.sub(r'^#+\s*', '', primera).strip()
                contenido = "\n".join(lineas[1:]).strip() or primera
            else:
                titulo = filename.replace(".md", "").capitalize()
                contenido = bloque

            secciones.append(DocSection(
                documento=filename,
                titulo=titulo,
                contenido=contenido
            ))

    return secciones


def recuperar_documentacion(consulta: str, top_k: int = 2) -> List[DocSection]:
    """
    Busca determinísticamente las secciones más relevantes para la consulta.
    Retorna lista vacía si la coincidencia es insuficiente.
    """
    query_tokens = _tokenize(consulta)
    if not query_tokens:
        return []

    secciones = cargar_secciones_autorizadas()
    if not secciones:
        return []

    resultados: List[DocSection] = []

    for sec in secciones:
        titulo_tokens = _tokenize(sec.titulo)
        cuerpo_tokens = _tokenize(sec.contenido)

        # Ponderación: coincidir en el título otorga mayor relevancia
        match_titulo = len(query_tokens.intersection(titulo_tokens))
        match_cuerpo = len(query_tokens.intersection(cuerpo_tokens))

        if match_titulo == 0 and match_cuerpo == 0:
            continue

        score = (match_titulo * 3.0) + (match_cuerpo * 1.0)
        # Normalizar contra el tamaño de la consulta
        score_norm = score / max(len(query_tokens), 1)

        if score_norm >= 0.5:  # Umbral mínimo de relevancia
            sec.score = round(score_norm, 2)
            resultados.append(sec)

    # Ordenar descendente por score
    resultados.sort(key=lambda s: s.score, reverse=True)
    return resultados[:top_k]
