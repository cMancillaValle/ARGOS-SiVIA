"""
backend/data/generar_layout.py
Genera el layout visual esquemático de TransMilenio (mapaTM) para las 126 estaciones
y crea el archivo frontend/js/transmilenio-layout.js.
"""

import json
import os

catalogo_path = os.path.join(os.path.dirname(__file__), 'estaciones_transmilenio.json')
with open(catalogo_path, 'r', encoding='utf-8') as f:
    catalogo = json.load(f)

estaciones = {e['codigo']: e for e in catalogo['estaciones']}
troncales = {t['id']: t for t in catalogo['troncales']}

# Coordenadas esquemáticas basadas en la topología de mapaTM
# Lienzo viewBox: { width: 1750, height: 1100 }
layout_stations = {}

def add_station(codigo, x, y, label_pos="right", interchange=False):
    if codigo in estaciones:
        layout_stations[codigo] = {
            "x": round(x, 1),
            "y": round(y, 1),
            "labelPosition": label_pos,
            "labelOffsetX": 10 if label_pos == "right" else (-10 if label_pos == "left" else 0),
            "labelOffsetY": 4 if label_pos in ("right", "left") else (-10 if label_pos == "top" else 14),
            "interchange": interchange,
            "tipo": estaciones[codigo].get("tipo", "estacion"),
            "troncalId": estaciones[codigo].get("troncal_id", "")
        }

# 1. TRONCAL B (Norte): Eje horizontal superior (Y = 190)
# De izquierda (Norte) hacia la derecha (Centro)
# Portal Norte (TM-B-01) en X=110, Héroes (TM-B-15) en X=530
b_codes = [f"TM-B-{i:02d}" for i in range(1, 16)]
x_b_start = 110
x_b_step = 30
for idx, code in enumerate(b_codes):
    pos_y = 190
    pos_x = x_b_start + idx * x_b_step
    # Héroes es intermedio hacia Caracas
    is_inter = (code in ("TM-B-01", "TM-B-12", "TM-B-15"))
    lpos = "top" if idx % 2 == 0 else "bottom"
    if code == "TM-B-01":
        lpos = "top"
    add_station(code, pos_x, pos_y, label_pos=lpos, interchange=is_inter)

# 2. TRONCAL A (Caracas Centro): Continuación de B en Y = 190
# De Calle 76 (TM-A-01, X=570) hasta Tercer Milenio (TM-A-13, X=1030)
a_codes = [f"TM-A-{i:02d}" for i in range(1, 14)]
x_a_start = 570
x_a_step = 38
for idx, code in enumerate(a_codes):
    pos_y = 190
    pos_x = x_a_start + idx * x_a_step
    is_inter = (code in ("TM-A-10", "TM-A-12"))
    lpos = "bottom" if idx % 2 == 1 else "top"
    if code == "TM-A-12":
        lpos = "top"  # Av Jimenez
    add_station(code, pos_x, pos_y, label_pos=lpos, interchange=is_inter)

# 3. TRONCAL C (Suba): Diagonal que arranca en Portal Suba (X=160, Y=620)
# Sube vertical hacia Y=480, luego diagonal hacia X=360, Y=330, y conecta con Calle 80 / NQS en X=440, Y=330
c_specs = [
    ("TM-C-01", 160, 620, "left", True),    # Portal Suba
    ("TM-C-02", 160, 580, "left", False),   # La Campiña
    ("TM-C-03", 160, 545, "left", False),   # Suba - TV 91
    ("TM-C-04", 160, 510, "left", False),   # 21 Ángeles
    ("TM-C-05", 160, 475, "left", False),   # Gratamira
    ("TM-C-06", 185, 440, "left", True),    # Suba AV Boyacá
    ("TM-C-07", 215, 410, "left", False),   # Niza - Calle 127
    ("TM-C-08", 245, 380, "left", False),   # Humedal Córdoba
    ("TM-C-09", 280, 355, "top", False),    # Puente Largo
    ("TM-C-10", 325, 355, "top", False),    # Suba - CL 100
    ("TM-C-11", 370, 355, "top", False),    # Rionegro
    ("TM-C-12", 415, 355, "top", False),    # San Martín
]
for code, x, y, lp, inter in c_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 4. TRONCAL D (Calle 80): Horizontal en Y=730 desde Portal 80,
# sube vertical hasta X=280, Y=470, luego diagonal a Escuela Militar (X=460, Y=355) y Polo (X=500, Y=290)
d_specs = [
    ("TM-D-01", 280, 750, "left", True),    # Portal 80
    ("TM-D-02", 280, 715, "left", False),   # Quirigua
    ("TM-D-03", 280, 680, "left", False),   # Carrera 90
    ("TM-D-04", 280, 645, "left", True),    # Avenida Cali
    ("TM-D-05", 280, 610, "left", False),   # Granja - KR 77
    ("TM-D-06", 280, 575, "left", False),   # Minuto de Dios
    ("TM-D-07", 310, 540, "left", False),   # Boyacá
    ("TM-D-08", 345, 505, "left", False),   # Ferias
    ("TM-D-09", 380, 470, "left", True),    # Avenida 68
    ("TM-D-10", 435, 400, "right", True),   # Escuela Militar
    ("TM-D-11", 500, 310, "right", False),  # Polo
]
for code, x, y, lp, inter in d_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 5. TRONCAL E (NQS Central):
# Corre horizontal por la NQS (Y=440) desde Castellana/Chile hacia el oriente/sur
# Cruza bajo Calle 80 y Caracas, y se une en Paloquemao/CAD
e_specs = [
    ("TM-G-10", 550, 440, "bottom", False), # Avenida Chile
    ("TM-E-07", 600, 440, "top", False),    # 7 de Agosto (NQS Calle 75)
    ("TM-E-04", 655, 440, "bottom", False), # Simón Bolívar
    ("TM-E-05", 715, 440, "top", False),    # Campín - UAN
    ("TM-E-06", 780, 440, "bottom", False), # Universidad Nacional
    ("TM-G-09", 860, 440, "top", True),     # CAD
    ("TM-G-08", 930, 440, "bottom", False), # Paloquemao
    ("TM-E-08", 1080, 340, "top", False),   # Guatoque - Veraguas
    ("TM-E-09", 1195, 490, "top", False),   # NQS Calle 30 Sur
    ("TM-E-10", 1235, 520, "top", False),   # NQS Calle 38A Sur
]
for code, x, y, lp, inter in e_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 6. TRONCAL K (Calle 26 - El Dorado):
# Corre desde Portal El Dorado (X=730, Y=870) hacia el norte vertical por Calle 26 hasta Y=510,
# luego cruza en diagonal hacia Centro Memoria (X=930, Y=330) y conecta con Caracas (Calle 26 TM-A-10)
k_specs = [
    ("TM-K-01", 730, 890, "left", True),    # Portal El Dorado
    ("TM-K-02", 730, 845, "left", False),   # Modelia
    ("TM-K-03", 730, 800, "left", False),   # Normandía
    ("TM-K-04", 730, 755, "left", False),   # Avenida Rojas
    ("TM-K-05", 730, 710, "left", False),   # El Tiempo - Maloka
    ("TM-K-06", 730, 665, "left", False),   # Salitre - El Greco
    ("TM-K-07", 730, 620, "left", False),   # CAN
    ("TM-K-08", 730, 575, "left", False),   # Gobernación
    ("TM-K-09", 760, 535, "right", False),  # Corferias
    ("TM-K-10", 800, 495, "right", False),  # Ciudad Universitaria
    ("TM-K-11", 870, 375, "top", True),     # Centro Memoria
]
for code, x, y, lp, inter in k_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 7. TRONCAL F (Américas):
# Desde Portal Américas (X=1170, Y=800) sube por Américas,
# cruza diagonal hacia Ricaurte (X=985, Y=440) y conecta con Caracas y Eje Ambiental
f_specs = [
    ("TM-F-01", 1170, 810, "top", True),    # Portal Américas
    ("TM-F-12", 1125, 810, "bottom", False),# Patio Bonito
    ("TM-F-13", 1060, 810, "bottom", False),# Biblioteca Tintal
    ("TM-F-14", 1075, 755, "left", False),  # Transversal 86
    ("TM-F-15", 1075, 715, "left", False),  # Av. Cali - Villavicencio
    ("TM-F-02", 1060, 670, "left", True),   # Banderas
    ("TM-F-03", 1045, 630, "left", False),  # Mandalay
    ("TM-F-04", 1030, 590, "right", False), # Mundo Aventura
    ("TM-F-05", 1005, 555, "right", False), # Marsella
    ("TM-F-06", 985, 520, "right", False),  # Pradera
    ("TM-F-07", 965, 485, "left", False),   # Distrito Grafiti (Américas KR 53A)
    ("TM-F-08", 965, 450, "left", False),   # Puente Aranda
    ("TM-F-09", 965, 415, "left", False),   # Carrera 43
    ("TM-F-10", 965, 380, "left", False),   # CDS - Carrera 32
    ("TM-F-11", 985, 340, "right", True),   # Ricaurte (Intercambio con Calle 13 / NQS)
]
for code, x, y, lp, inter in f_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 8. TRONCAL G (NQS Sur):
# Conecta desde NQS en Comuneros (X=1080, Y=440), baja diagonal por Autopista Sur hasta Portal Sur (X=1210, Y=740),
# y sigue hacia Soacha (San Mateo X=1380, Y=890)
g_specs = [
    ("TM-G-07", 1080, 440, "bottom", True),  # Comuneros
    ("TM-G-06", 1120, 440, "top", False),    # Santa Isabel
    ("TM-G-05", 1160, 465, "top", False),    # SENA
    ("TM-G-02", 1210, 555, "right", True),   # General Santander
    ("TM-G-04", 1210, 595, "right", False),  # Alquería
    ("TM-G-03", 1210, 635, "right", False),  # Venecia
    ("TM-G-15", 1210, 670, "right", False),  # Sevillana
    ("TM-G-13", 1210, 705, "right", False),  # Madelena
    ("TM-G-14", 1210, 740, "right", False),  # Perdomo
    ("TM-G-01", 1210, 785, "left", True),    # Portal Sur
    ("TM-G-11", 1320, 880, "right", False),  # Terreros - Hospital C.V.
    ("TM-G-12", 1380, 930, "right", True),   # San Mateo - C.C. Unisur
]
for code, x, y, lp, inter in g_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 9. TRONCAL H (Caracas Sur):
# Ramal desde Tercer Milenio / Hospital (X=1050, Y=260) bajando diagonal por la Caracas hacia Usme y Tunal
h_specs = [
    ("TM-H-06", 1050, 260, "right", False), # Hospital
    ("TM-H-05", 1150, 260, "top", False),   # Restrepo
    ("TM-H-07", 1200, 290, "right", False), # Olaya
    ("TM-H-08", 1240, 325, "right", False), # Quiroga
    ("TM-H-04", 1280, 365, "right", False), # Calle 40 Sur
    ("TM-H-09", 1320, 410, "left", False),  # Santa Lucía
    ("TM-H-10", 1360, 455, "left", False),  # Socorro
    ("TM-H-11", 1395, 490, "left", False),  # Consuelo
    ("TM-H-03", 1430, 490, "top", True),    # Molinos
    ("TM-H-12", 1465, 490, "bottom", False),# Danubio
    ("TM-H-15", 1495, 490, "top", False),   # Santa Librada
    ("TM-H-16", 1525, 490, "bottom", False),# Yomasa
    ("TM-H-01", 1565, 490, "right", True),  # Portal Usme
    # Ramal hacia Portal Tunal (desde Santa Lucía / Socorro hacia abajo)
    ("TM-H-13", 1360, 520, "right", False), # Parque
    ("TM-H-14", 1360, 560, "right", False), # Biblioteca Tunal
    ("TM-H-02", 1360, 605, "right", True),  # Portal Tunal
]
for code, x, y, lp, inter in h_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 10. TRONCAL J (Eje Ambiental):
# Al oriente de Av. Jiménez hacia Las Aguas / Universidades (Y = 120 a 70, X = 985)
j_specs = [
    ("TM-J-01", 985, 120, "right", False),  # Museo del Oro
    ("TM-J-02", 985, 60, "right", True),    # Aguas / Universidades
]
for code, x, y, lp, inter in j_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# 11. TRONCAL L (Carrera 10):
# Corre de norte a sur por la Carrera 10 desde San Diego (X=870, Y=140),
# pasa por San Victorino y Hospitales, y baja hasta Portal 20 de Julio (X=1450, Y=140)
l_specs = [
    ("TM-L-02", 870, 140, "top", True),     # San Diego
    ("TM-L-04", 930, 140, "bottom", False), # Las Nieves
    ("TM-L-03", 985, 140, "bottom", False), # San Victorino
    ("TM-L-05", 1060, 140, "top", False),   # San Bernardo
    ("TM-L-06", 1120, 140, "bottom", False),# Policarpa
    ("TM-L-07", 1180, 140, "top", False),   # Ciudad Jardín - UAN
    ("TM-L-08", 1250, 140, "bottom", False),# Av. 1° de Mayo
    ("TM-L-09", 1330, 140, "top", False),   # Country Sur
    ("TM-L-01", 1450, 140, "right", True),  # Portal 20 de Julio
]
for code, x, y, lp, inter in l_specs:
    add_station(code, x, y, label_pos=lp, interchange=inter)

# VERIFICACIÓN DE TODAS LAS ESTACIONES DEL CATÁLOGO
faltantes = [cod for cod in estaciones if cod not in layout_stations]
print(f"Estaciones mapeadas en layout: {len(layout_stations)} / {len(estaciones)}")
if faltantes:
    print(f"ADVERTENCIA - Faltantes: {faltantes}")

# DEFINICIÓN DE CORREDORES / RUTAS SVG (PATHS)
corridors = [
    {
        "id": "B",
        "troncalId": "B",
        "label": "Troncal Norte (B)",
        "color": "#009639",
        "path": "M 110 190 L 530 190",
        "stationIds": [f"TM-B-{i:02d}" for i in range(1, 16)]
    },
    {
        "id": "A",
        "troncalId": "A",
        "label": "Troncal Caracas (A)",
        "color": "#E8001D",
        "path": "M 530 190 L 1030 190",
        "stationIds": [f"TM-A-{i:02d}" for i in range(1, 14)]
    },
    {
        "id": "C",
        "troncalId": "C",
        "label": "Troncal Suba (C)",
        "color": "#F4A900",
        "path": "M 160 620 L 160 480 L 280 355 L 430 355",
        "stationIds": [c[0] for c in c_specs]
    },
    {
        "id": "D",
        "troncalId": "D",
        "label": "Troncal Calle 80 (D)",
        "color": "#6F2282",
        "path": "M 280 750 L 280 610 L 415 470 L 460 355 L 500 310 L 530 190",
        "stationIds": [d[0] for d in d_specs]
    },
    {
        "id": "E",
        "troncalId": "E",
        "label": "Troncal NQS Central (E)",
        "color": "#0FA3D8",
        "path": "M 530 440 L 930 440 L 985 340 L 1080 340 L 1080 440 L 1235 520",
        "stationIds": [e[0] for e in e_specs]
    },
    {
        "id": "K",
        "troncalId": "K",
        "label": "Troncal Calle 26 (K)",
        "color": "#F37021",
        "path": "M 730 890 L 730 580 L 870 375 L 870 190",
        "stationIds": [k[0] for k in k_specs]
    },
    {
        "id": "F",
        "troncalId": "F",
        "label": "Troncal Américas (F)",
        "color": "#C8102E",
        "path": "M 1170 810 L 1060 810 L 1075 740 L 1060 670 L 965 470 L 965 370 L 985 340",
        "stationIds": [f[0] for f in f_specs]
    },
    {
        "id": "G",
        "troncalId": "G",
        "label": "Troncal NQS Sur (G)",
        "color": "#0FA3D8",
        "path": "M 1080 440 L 1210 520 L 1210 785 L 1380 930",
        "stationIds": [g[0] for g in g_specs]
    },
    {
        "id": "H",
        "troncalId": "H",
        "label": "Troncal Caracas Sur (H)",
        "color": "#E8001D",
        "path": "M 1030 190 L 1050 260 L 1150 260 L 1320 410 L 1400 490 L 1565 490",
        "stationIds": [h[0] for h in h_specs if h[0] not in ("TM-H-13", "TM-H-14", "TM-H-02")]
    },
    {
        "id": "H_TUNAL",
        "troncalId": "H",
        "label": "Caracas Sur - Ramal Tunal (H)",
        "color": "#E8001D",
        "path": "M 1360 455 L 1360 605",
        "stationIds": ["TM-H-13", "TM-H-14", "TM-H-02"]
    },
    {
        "id": "J",
        "troncalId": "J",
        "label": "Eje Ambiental (J)",
        "color": "#00B5E2",
        "path": "M 985 190 L 985 60",
        "stationIds": [j[0] for j in j_specs]
    },
    {
        "id": "L",
        "troncalId": "L",
        "label": "Troncal Carrera 10 (L)",
        "color": "#8A9EA7",
        "path": "M 870 140 L 1450 140",
        "stationIds": [l[0] for l in l_specs]
    }
]

# CONEXIONES / TRANSBORDOS ESTRATÉGICOS
connections = [
    {
        "id": "transbordo-jimenez",
        "label": "Transbordo Av. Jiménez - Eje Ambiental",
        "stationIds": ["TM-A-12", "TM-J-01"],
        "path": "M 985 190 L 985 140"
    },
    {
        "id": "transbordo-san-diego",
        "label": "Conexión Centro Memoria - San Diego",
        "stationIds": ["TM-K-11", "TM-L-02"],
        "path": "M 870 375 L 870 140"
    },
    {
        "id": "transbordo-ricaurte",
        "label": "Transbordo Ricaurte (Américas / NQS)",
        "stationIds": ["TM-F-11", "TM-E-08"],
        "path": "M 985 340 L 1080 340"
    },
    {
        "id": "transbordo-heroes",
        "label": "Héroes / Autonorte / Caracas",
        "stationIds": ["TM-B-15", "TM-A-01"],
        "path": "M 530 190 L 570 190"
    },
    {
        "id": "transbordo-militar",
        "label": "Escuela Militar / NQS / Calle 80",
        "stationIds": ["TM-D-10", "TM-C-12"],
        "path": "M 435 400 L 415 355"
    }
]

layout_data = {
    "viewBox": { "width": 1750, "height": 1050 },
    "stations": layout_stations,
    "corridors": corridors,
    "connections": connections
}

# Guardar en JSON de backend
json_out = os.path.join(os.path.dirname(__file__), 'mapa_transmilenio_layout.json')
with open(json_out, 'w', encoding='utf-8') as f:
    json.dump(layout_data, f, indent=2, ensure_ascii=False)
print(f"Generado {json_out} correctamente.")

# Guardar en JS para frontend local
frontend_js = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'js', 'transmilenio-layout.js'))
with open(frontend_js, 'w', encoding='utf-8') as f:
    f.write(f"/**\n * frontend/js/transmilenio-layout.js\n * Layout esquemático oficial de TransMilenio SiViA basado en mapaTM.\n * 100% libre de coordenadas GPS y dependencias externas.\n */\n\nconst TRANSMILENIO_LAYOUT = {json.dumps(layout_data, indent=2, ensure_ascii=False)};\n\nif (typeof module !== 'undefined' && module.exports) {{\n  module.exports = TRANSMILENIO_LAYOUT;\n}}\n")
print(f"Generado {frontend_js} correctamente.")
