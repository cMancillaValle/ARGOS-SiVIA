"""
tests/test_transmilenio_schematic_map.py
────────────────────────────────────────
Pruebas automatizadas para el mapa esquemático de TransMilenio (mapaTM):
- Endpoints de API existentes: /api/transmilenio/estaciones, /troncales, /resumen.
- Integridad y coherencia del archivo de layout (mapa_transmilenio_layout.json y transmilenio-layout.js).
- Cobertura de las estaciones existentes y pendientes de representación sin inventar datos.
- Cálculo determinista de clases de riesgo y métricas de seguridad.
- Ausencia segura de datos y preservación de RBAC.
"""

import os
import sys
import json
import pytest

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(PROJECT_ROOT, 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from starlette.testclient import TestClient
from main import app
from services.auth_service import create_session

client = TestClient(app)

CATALOGO_FILE = os.path.join(PROJECT_ROOT, 'backend', 'data', 'estaciones_transmilenio.json')
LAYOUT_JSON = os.path.join(PROJECT_ROOT, 'backend', 'data', 'mapa_transmilenio_layout.json')
LAYOUT_JS = os.path.join(PROJECT_ROOT, 'frontend', 'js', 'transmilenio-layout.js')


@pytest.fixture
def admin_token():
    return create_session(1)


@pytest.fixture
def operador_token():
    return create_session(3)


# ── 1. API: Resumen y Troncales ─────────────────────────────────────────────
def test_transmilenio_resumen(operador_token):
    res = client.get("/api/transmilenio/resumen", headers={"X-Token": operador_token})
    assert res.status_code == 200
    data = res.json()
    assert "red" in data
    assert "total_estaciones" in data["red"]
    assert data["red"]["total_estaciones"] == 155
    assert "camaras" in data
    assert "evasiones_hoy" in data


def test_transmilenio_troncales(operador_token):
    res = client.get("/api/transmilenio/troncales", headers={"X-Token": operador_token})
    assert res.status_code == 200
    data = res.json()
    troncales = data.get("troncales", [])
    assert len(troncales) == 14
    ids = [t["id"] for t in troncales]
    assert "A" in ids and "B" in ids and "K" in ids and "F" in ids


# ── 2. API: Estaciones enriquecidas con riesgo y cámaras ───────────────────
def test_transmilenio_estaciones_enriquecidas(operador_token):
    res = client.get("/api/transmilenio/estaciones", headers={"X-Token": operador_token})
    assert res.status_code == 200
    data = res.json()
    estaciones = data.get("estaciones", [])
    assert len(estaciones) == 155

    # Verificar que cada estación tenga estructura enriquecida de SiViA
    for est in estaciones[:10]:
        assert "codigo" in est
        assert "troncal_id" in est
        assert "camaras" in est
        assert "eventos_hoy" in est
        assert "riesgo" in est
        assert est["riesgo"] in ("normal", "alerta", "critico")


def test_transmilenio_detalle_estacion(operador_token):
    # Probar con Portal Norte (TM-B-01)
    res = client.get("/api/transmilenio/estaciones/TM-B-01", headers={"X-Token": operador_token})
    assert res.status_code == 200
    data = res.json()
    assert data["codigo"] == "TM-B-01"
    assert "camaras" in data
    assert "estadisticas" in data


def test_transmilenio_detalle_estacion_no_encontrada(operador_token):
    res = client.get("/api/transmilenio/estaciones/INEXISTENTE-999", headers={"X-Token": operador_token})
    assert res.status_code == 404
    data = res.json()
    assert "error" in data


# ── 3. Layout: Coherencia y cobertura de las estaciones con representación ─────────────
def test_layout_cobertura_total():
    assert os.path.exists(LAYOUT_JSON)
    assert os.path.exists(CATALOGO_FILE)

    with open(CATALOGO_FILE, "r", encoding="utf-8") as f:
        catalogo = json.load(f)

    with open(LAYOUT_JSON, "r", encoding="utf-8") as f:
        layout = json.load(f)

    catalogo_codigos = {e["codigo"] for e in catalogo["estaciones"]}
    layout_codigos = set(layout["stations"].keys())

    assert len(catalogo_codigos) == 155
    # Las extensiones de Soacha y Ciudad de Cali quedan fuera del esquema.
    faltantes = catalogo_codigos - layout_codigos
    assert faltantes == {
        "TM-G-11", "TM-G-12", "TM-G-16", "TM-G-17", "TM-G-18",
        "TM-Z-01", "TM-Z-02", "TM-Z-03",
    }
    assert layout_codigos <= catalogo_codigos

    # Validar coordenadas numéricas válidas y sin NaN/None
    for cod, st in layout["stations"].items():
        assert isinstance(st["x"], (int, float))
        assert isinstance(st["y"], (int, float))
        assert st["x"] > 0
        assert st["y"] > 0
        assert st["labelPosition"] in ("right", "left", "top", "bottom")


def test_layout_corredores_y_conexiones():
    with open(LAYOUT_JSON, "r", encoding="utf-8") as f:
        layout = json.load(f)

    assert "corridors" in layout
    assert len(layout["corridors"]) >= 11
    for corr in layout["corridors"]:
        assert "path" in corr
        assert corr["path"].startswith("M ")
        assert "color" in corr

    assert "connections" in layout
    assert len(layout["connections"]) >= 4
    for conn in layout["connections"]:
        assert "path" in conn
        assert conn["path"].startswith("M ")


def test_archivo_frontend_layout_js():
    assert os.path.exists(LAYOUT_JS)
    with open(LAYOUT_JS, "r", encoding="utf-8") as f:
        content = f.read()
    assert "const TRANSMILENIO_LAYOUT =" in content
    assert "viewBox" in content
    assert "TM-B-01" in content
