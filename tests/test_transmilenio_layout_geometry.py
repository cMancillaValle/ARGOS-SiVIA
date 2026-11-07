"""Validaciones aisladas de la geometria C4. No abre SQLite."""

import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"
EXCLUDED = {
    "TM-G-11", "TM-G-12", "TM-G-16", "TM-G-17", "TM-G-18",
    "TM-Z-01", "TM-Z-02", "TM-Z-03",
}


def read_data():
    catalog = json.loads((DATA / "estaciones_transmilenio.json").read_text(encoding="utf-8"))
    layout = json.loads((DATA / "mapa_transmilenio_layout.json").read_text(encoding="utf-8"))
    return catalog, layout


def test_catalog_and_svg_coverage():
    catalog, layout = read_data()
    codes = [item["codigo"] for item in catalog["estaciones"]]
    ids = [item["id"] for item in catalog["estaciones"]]
    assert len(codes) == len(ids) == 155
    assert len(set(codes)) == len(set(ids)) == 155
    assert len(catalog["troncales"]) == 14
    assert len(layout["stations"]) == 147
    assert set(codes) - set(layout["stations"]) == EXCLUDED


def test_corridors_and_nodes_are_consistent():
    _, layout = read_data()
    positions = layout["stations"]
    seen = []
    route_ids = []
    for route in layout["corridors"]:
        route_ids.append(route["id"])
        assert route["path"].startswith("M ")
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", route["color"])
        assert set(route["stationIds"]) <= set(positions)
        seen.extend(route["stationIds"])
    assert len(set(route_ids)) == len(route_ids)
    assert len(seen) == len(set(seen))
    assert set(seen) | {"TM-N-01"} == set(positions)
    assert len({(item["x"], item["y"]) for item in positions.values()}) == len(positions)
    assert layout["viewBox"] == {"width": 1100, "height": 850}


def test_frontend_artifact_matches_backend():
    _, layout = read_data()
    frontend = (ROOT / "frontend/js/transmilenio-layout.js").read_text(encoding="utf-8")
    payload = re.search(r"const TRANSMILENIO_LAYOUT = (\{.*\});", frontend, re.S)
    assert payload
    assert json.loads(payload.group(1)) == layout


def test_no_typographic_dashes_in_geometry_files():
    for file in (DATA / "generar_layout.py", DATA / "mapa_transmilenio_layout.json",
                 ROOT / "frontend/js/transmilenio-layout.js"):
        content = file.read_text(encoding="utf-8")
        assert "\u2013" not in content
        assert "\u2014" not in content


def segment_distance(point, start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    fraction = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy)
    fraction = max(0, min(1, fraction / length_squared)) if length_squared else 0
    projection = (start[0] + fraction * dx, start[1] + fraction * dy)
    return math.dist(point, projection)


def route_segments(path):
    numbers = [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", path)]
    assert len(numbers) >= 4 and len(numbers) % 2 == 0
    points = list(zip(numbers[::2], numbers[1::2]))
    return list(zip(points, points[1:]))


def test_all_nodes_lie_on_their_own_routes():
    catalog, layout = read_data()
    names = {item["codigo"]: item["nombre"] for item in catalog["estaciones"]}
    routes = {}
    for route in layout["corridors"]:
        for code in route["stationIds"]:
            routes.setdefault(code, []).append(route)
    # La troncal N tiene un nodo sobre el eje central sin recorrido propio.
    routes["TM-N-01"] = [next(route for route in layout["corridors"] if route["id"] == "E")]
    failures = []
    # El trazo mide 6.5 unidades. La tolerancia de 0.25 solo cubre
    # el redondeo de las coordenadas a una decimal.
    tolerance = 0.25
    for code, station in layout["stations"].items():
        point = (station["x"], station["y"])
        candidates = [
            (segment_distance(point, start, end), route["id"], index, start, end)
            for route in routes[code]
            for index, (start, end) in enumerate(route_segments(route["path"]))
        ]
        distance, route_id, index, start, end = min(candidates)
        if distance > tolerance:
            failures.append({
                "codigo": code, "nombre": names[code],
                "troncal": station["troncalId"], "coordenadas": point,
                "distancia": round(distance, 3),
                "segmento": (route_id, index, start, end),
            })
    assert not failures, json.dumps(failures, ensure_ascii=False, indent=2)


def test_calle_75_and_americas_coverage():
    catalog, layout = read_data()
    codes = {item["codigo"] for item in catalog["estaciones"]}
    assert "TM-E-12" in codes
    assert "TM-E-12" in layout["stations"]
    americas = {code for code in codes if code.startswith("TM-F-")}
    assert len(americas) == 19
    assert americas <= set(layout["stations"])
    f_route = next(route for route in layout["corridors"] if route["id"] == "F")
    assert set(f_route["stationIds"]) == americas


def test_all_labels_have_supported_positions():
    _, layout = read_data()
    assert {item["labelPosition"] for item in layout["stations"].values()} <= {
        "top", "bottom", "left", "right",
    }
