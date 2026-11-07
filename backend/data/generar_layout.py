"""Genera el layout C4 a partir del catalogo y la geometria de referencia."""

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent
ROOT = DATA.parents[1]
catalog = json.loads((DATA / "estaciones_transmilenio.json").read_text(encoding="utf-8"))
stations = {item["codigo"]: item for item in catalog["estaciones"]}
positions = {}
corridors = []
colors = {
    "A": "#283788", "B": "#74B51C", "C": "#FFC400", "D": "#76529C",
    "E": "#B77A00", "F": "#E40022", "G": "#00A6D8", "H": "#FF9300",
    "J": "#E8ABB9", "K": "#D4AD70", "L": "#00A3A0", "M": "#C00092",
}


def path(points):
    return "M " + " L ".join(f"{x} {y}" for x, y in points)


def interpolate(points, fraction):
    segments = [math.dist(a, b) for a, b in zip(points, points[1:])]
    distance = sum(segments) * fraction
    for (x1, y1), (x2, y2), segment in zip(points, points[1:], segments):
        if distance <= segment:
            ratio = distance / segment if segment else 0
            return x1 + (x2 - x1) * ratio, y1 + (y2 - y1) * ratio
        distance -= segment
    return points[-1]


def place(code, x, y, index=0, interchange=False, label=None):
    if code not in stations or code in positions:
        raise ValueError(f"Codigo inexistente o repetido: {code}")
    item = stations[code]
    label = label or ("top" if index % 2 == 0 else "bottom")
    positions[code] = {
        "x": round(x, 1), "y": round(y, 1),
        "labelPosition": label,
        "labelOffsetX": -12 if label == "left" else 10,
        "labelOffsetY": -12 if label == "top" else 16 if label == "bottom" else 2,
        "interchange": interchange or item.get("tipo") == "portal",
        "tipo": item.get("tipo", "estacion"), "troncalId": item["troncal_id"],
    }


def add_route(route_id, trunk, label, points, codes, interchanges=(),
              start_inset=0, end_inset=0):
    if len(points) < 2 or not codes:
        raise ValueError(f"Recorrido incompleto: {route_id}")
    total_length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    for index, code in enumerate(codes):
        fraction = index / (len(codes) - 1) if len(codes) > 1 else 0.5
        fraction = start_inset / total_length + fraction * (
            1 - (start_inset + end_inset) / total_length)
        x, y = interpolate(points, fraction)
        before = interpolate(points, max(0, fraction - 0.002))
        after = interpolate(points, min(1, fraction + 0.002))
        vertical = abs(after[1] - before[1]) > abs(after[0] - before[0]) * 1.2
        label = ("right" if index % 2 == 0 else "left") if vertical else (
            "top" if index % 2 == 0 else "bottom")
        place(code, x, y, index, code in interchanges, label)
    corridors.append({
        "id": route_id, "troncalId": trunk, "label": label,
        "color": colors[trunk], "path": path(points), "stationIds": codes,
    })


# Topologia esquematica de la imagen docs/referencias/mapa_transmilenio_referencia.png.
# Los puntos no son coordenadas geograficas.
add_route("B", "B", "Norte", [(35, 244), (380, 244)],
          ["TM-B-17", "TM-B-16"] + [f"TM-B-{i:02d}" for i in range(1, 16)],
          end_inset=12)
add_route("A", "A", "Caracas Centro", [(380, 244), (714, 244)],
          [f"TM-A-{i:02d}" for i in range(1, 14)], ("TM-A-12",), 6)
add_route("C", "C", "Suba", [(156, 489), (156, 394), (210, 352), (370, 352)],
          [f"TM-C-{i:02d}" for i in range(1, 15)], end_inset=30)
add_route("D", "D", "Calle 80", [(260, 568), (260, 454), (399, 319), (399, 244)],
          [f"TM-D-{i:02d}" for i in range(1, 14)], ("TM-D-10",))
add_route("E", "E", "NQS Central", [(325, 244), (325, 296), (370, 352), (712, 352)],
          ["TM-E-11", "TM-E-12", "TM-G-10", "TM-E-07", "TM-E-04",
           "TM-E-13", "TM-E-05", "TM-E-06", "TM-E-14", "TM-G-09",
           "TM-G-08", "TM-E-08", "TM-E-09", "TM-E-10"],
          ("TM-G-09",), start_inset=14)
# Separar nodos cercanos en el cruce central sin mover los recorridos.
positions["TM-G-08"]["x"] = 626
add_route("F", "F", "Americas", [(670, 244), (670, 450), (752, 541),
                                (752, 600), (805, 600)],
          ["TM-F-11", "TM-F-17", "TM-F-19", "TM-F-18", "TM-F-10",
           "TM-F-09", "TM-F-08", "TM-F-07", "TM-F-06", "TM-F-05",
           "TM-F-16", "TM-F-04", "TM-F-03", "TM-F-02", "TM-F-15",
           "TM-F-14", "TM-F-13", "TM-F-12", "TM-F-01"], ("TM-F-11",))
add_route("G", "G", "NQS Sur", [(712, 352), (756, 352), (825, 419),
                              (825, 545), (932, 640)],
          ["TM-G-07", "TM-G-06", "TM-G-05", "TM-G-02", "TM-G-04",
           "TM-G-03", "TM-G-15", "TM-G-13", "TM-G-14", "TM-G-01"],
          ("TM-G-07",), 12)
add_route("H", "H", "Caracas Sur", [(714, 244), (792, 244), (935, 388),
                                  (935, 423), (968, 500)],
          ["TM-H-06", "TM-H-19", "TM-H-18", "TM-H-17", "TM-H-05",
           "TM-H-07", "TM-H-08", "TM-H-04", "TM-H-09", "TM-H-10",
           "TM-H-11", "TM-H-03", "TM-H-12", "TM-H-15", "TM-H-16",
           "TM-H-01"], start_inset=12)
add_route("H_TUNAL", "H", "Ramal Tunal", [(888, 340), (984, 340)],
          ["TM-H-13", "TM-H-14", "TM-H-02"], start_inset=17)
add_route("J", "J", "Eje Ambiental", [(670, 244), (670, 158), (630, 108)],
          ["TM-J-01", "TM-J-02"], start_inset=12)
add_route("K", "K", "Calle 26", [(525, 710), (525, 469), (614, 352),
                               (614, 108)],
          [f"TM-K-{i:02d}" for i in range(1, 15)], ("TM-K-11",))
add_route("L", "L", "Carrera 10", [(614, 171), (865, 171)],
          ["TM-L-02", "TM-L-04", "TM-L-03", "TM-L-10", "TM-L-05",
           "TM-L-06", "TM-L-07", "TM-L-08", "TM-L-09", "TM-L-01"])
add_route("M", "M", "Carrera 7", [(218, 171), (614, 171)], ["TM-M-01"])

# N no figura en la leyenda de la referencia. Su nodo esta sobre el eje central.
place("TM-N-01", 590, 352, interchange=True)

# Estas extensiones quedan consultables en el catalogo y fuera del SVG.
excluded = {"TM-G-11", "TM-G-12", "TM-G-16", "TM-G-17", "TM-G-18",
            "TM-Z-01", "TM-Z-02", "TM-Z-03"}
missing = set(stations) - set(positions)
if missing != excluded:
    raise ValueError(f"Cobertura inesperada: {sorted(missing)}")

connections = [
    {"id": "norte-caracas", "label": "Norte / Caracas",
     "stationIds": ["TM-B-15", "TM-A-01"], "path": "M 380 244 L 380 244"},
    {"id": "calle80-nqs", "label": "Calle 80 / NQS",
     "stationIds": ["TM-D-10", "TM-E-04"], "path": "M 370 352 L 370 352"},
    {"id": "nqs-calle26", "label": "NQS / Calle 26",
     "stationIds": ["TM-E-14", "TM-K-11"], "path": "M 614 352 L 614 352"},
    {"id": "caracas-americas", "label": "Caracas / Americas",
     "stationIds": ["TM-A-12", "TM-F-11"], "path": "M 670 244 L 670 244"},
    {"id": "nqs-sur", "label": "NQS Central / NQS Sur",
     "stationIds": ["TM-E-10", "TM-G-07"], "path": "M 712 352 L 712 352"},
]
layout = {"viewBox": {"width": 1100, "height": 850},
          "stations": positions, "corridors": corridors, "connections": connections}
payload = json.dumps(layout, indent=2, ensure_ascii=False)
(DATA / "mapa_transmilenio_layout.json").write_text(payload + "\n", encoding="utf-8")
(ROOT / "frontend/js/transmilenio-layout.js").write_text(
    "/** Layout C4 generado por backend/data/generar_layout.py. */\n\n"
    + "const TRANSMILENIO_LAYOUT = " + payload
    + ";\n\nif (typeof module !== 'undefined' && module.exports) {\n"
    + "  module.exports = TRANSMILENIO_LAYOUT;\n}\n", encoding="utf-8")
print(f"Estaciones representadas: {len(positions)} / {len(stations)}")
print(f"Fuera del esquema: {', '.join(sorted(excluded))}")
