import json
import os
import sys
import sqlite3
from datetime import date
from datetime import datetime

import pytest


PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
BACKEND_DIR = os.path.join(PROJECT_ROOT, 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from api.routers import transmilenio


CATALOG_PATH = os.path.join(BACKEND_DIR, 'data', 'estaciones_transmilenio.json')
LAYOUT_PATH = os.path.join(BACKEND_DIR, 'data', 'mapa_transmilenio_layout.json')
LAYOUT_JS_PATH = os.path.join(PROJECT_ROOT, 'frontend', 'js', 'transmilenio-layout.js')
MAP_VIEW_PATH = os.path.join(PROJECT_ROOT, 'frontend', 'views', 'mapa_transmilenio.html')
RENDERER_PATH = os.path.join(PROJECT_ROOT, 'frontend', 'js', 'transmilenio-schematic-map.js')
EXCLUDED_LAYOUT_CODES = {
    'TM-G-11', 'TM-G-12', 'TM-G-16', 'TM-G-17', 'TM-G-18',
    'TM-Z-01', 'TM-Z-02', 'TM-Z-03',
}


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / 'transmilenio-test.sqlite'
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE camaras (
            id INTEGER PRIMARY KEY,
            codigo_estacion TEXT,
            estacion TEXT NOT NULL,
            estado TEXT,
            codigo TEXT,
            ubicacion TEXT,
            ip TEXT,
            fps INTEGER,
            resolucion TEXT,
            instalada INTEGER
        );
        CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nombre TEXT);
        CREATE TABLE eventos (
            id INTEGER PRIMARY KEY,
            camara_id INTEGER NOT NULL,
            tipo TEXT,
            confianza REAL,
            estado TEXT,
            observaciones TEXT,
            detectado_en TEXT,
            operador_id INTEGER
        );
    ''')
    today = date.today().strftime('%Y-%m-%d')
    cameras = [
        (1, 'TM-B-07', 'Unknown legacy label', 'activa', 'CAM-1'),
        (2, None, 'Alcalá', 'offline', 'CAM-2'),
        (3, '', 'Alcalá - Colegio S. Tomás Dominicos', 'activa', 'CAM-3'),
        (4, 'TM-B-07', 'Alcalá', 'mantenimiento', 'CAM-4'),
        (5, 'UNKNOWN-CODE', 'Alcalá', 'activa', 'CAM-5'),
    ]
    conn.executemany(
        '''INSERT INTO camaras
           (id, codigo_estacion, estacion, estado, codigo, ubicacion, ip, fps, resolucion, instalada)
           VALUES (?, ?, ?, ?, ?, 'test', '127.0.0.1', 10, 'test', 1)''',
        cameras,
    )
    conn.executemany(
        '''INSERT INTO eventos
           (id, camara_id, tipo, confianza, estado, observaciones, detectado_en, operador_id)
           VALUES (?, ?, 'test', 0.9, 'confirmado', '', ?, NULL)''',
        [(index, index, f'{today} 10:00:00') for index in range(1, 6)],
    )
    conn.commit()
    conn.close()

    def connect_test_db():
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(transmilenio, '_get_db', connect_test_db)
    return path


def test_catalog_counts_codes_and_layout_coverage():
    with open(CATALOG_PATH, encoding='utf-8') as catalog_file:
        catalog = json.load(catalog_file)
    with open(LAYOUT_PATH, encoding='utf-8') as layout_file:
        layout = json.load(layout_file)
    with open(LAYOUT_JS_PATH, encoding='utf-8') as layout_js_file:
        layout_js = layout_js_file.read()

    stations = catalog['estaciones']
    codes = [station['codigo'] for station in stations]
    ids = [station['id'] for station in stations]
    assert len(stations) == 155
    assert len(catalog['troncales']) == 14
    assert len(set(codes)) == 155
    assert len(set(ids)) == 155
    assert set(layout['stations']) <= set(codes)
    assert set(codes) - set(layout['stations']) == EXCLUDED_LAYOUT_CODES
    import re
    browser_layout_codes = set(re.findall(r'"(TM-[A-Z]-\d{2})":\s*\{', layout_js))
    assert set(browser_layout_codes) <= set(codes)


def test_catalog_alias_types_and_dash_characters():
    with open(CATALOG_PATH, encoding='utf-8') as catalog_file:
        catalog = json.load(catalog_file)
    alias_owners = {}
    name_owners = {}
    for station in catalog['estaciones']:
        aliases = station.get('aliases', [])
        assert isinstance(aliases, list)
        assert all(isinstance(alias, str) for alias in aliases)
        for value in [station['nombre'], *aliases]:
            assert '\u2013' not in value
            assert '\u2014' not in value
            name_owners.setdefault(transmilenio._normalizar_nombre(value), set()).add(station['codigo'])
        for alias in aliases:
            alias_owners.setdefault(transmilenio._normalizar_nombre(alias), set()).add(station['codigo'])
    assert all(len(owners) == 1 for owners in alias_owners.values())
    assert all(len(owners) == 1 for owners in name_owners.values())


def test_catalog_operational_state_schema_and_evidence():
    with open(CATALOG_PATH, encoding='utf-8') as catalog_file:
        catalog = json.load(catalog_file)

    allowed = {
        'operativa', 'temporal', 'cerrada_temporalmente', 'historica', 'por_verificar'
    }
    assert len(catalog['estaciones']) == 155
    assert len(catalog['troncales']) == 14
    for station in catalog['estaciones']:
        assert station['estado_operativo'] in allowed
        source = station.get('estado_fuente')
        verified_on = station.get('estado_verificado_en')
        if station['estado_operativo'] == 'por_verificar':
            assert source is None
            assert verified_on is None
        else:
            assert source.startswith('https://')
            assert datetime.strptime(verified_on, '%Y-%m-%d').date()
        for relation in station.get('relaciones', []):
            assert relation['tipo_relacion']
            assert relation['codigo_relacionado'] in {
                item['codigo'] for item in catalog['estaciones']
            }


def test_renamed_stations_keep_historical_aliases():
    catalog = transmilenio._cargar_datos_estaciones()['estaciones']
    index = transmilenio._indice_estaciones(catalog)
    expected = {
        'TM-B-01': ('Portal Norte - Unicervantes', 'Portal Norte'),
        'TM-B-03': ('Calle 161', 'Cardio Infantil'),
        'TM-B-10': ('Pepe Sierra - Utel Universidad', 'Pepe Sierra'),
        'TM-B-12': ('Calle 100 - Marketmedios', 'Calle 100'),
        'TM-B-15': ('Héroes - Colmena Seguros', 'Héroes'),
        'TM-K-01': ('Portal El Dorado - C.C. Nuestro Bogotá', 'Portal El Dorado'),
    }
    for code, (name, alias) in expected.items():
        station = transmilenio._resolver_estacion(catalog, '', alias, index)
        assert station['codigo'] == code
        assert station['nombre'] == name
        assert transmilenio._resolver_estacion(catalog, code, 'irrelevant', index)['codigo'] == code


def test_camera_resolution_precedence_alias_and_no_duplicate(isolated_db):
    result = transmilenio.listar_estaciones(usuario={}).body
    payload = json.loads(result)
    station = next(item for item in payload['estaciones'] if item['codigo'] == 'TM-B-07')
    assert station['camaras'] == {'total': 4, 'activas': 2, 'offline': 1, 'mantenimiento': 1}
    assert station['eventos_hoy']['total_hoy'] == 4
    assert station['eventos_hoy']['confirmadas'] == 4


def test_camera_code_conflict_does_not_fall_back_to_name():
    catalog = transmilenio._cargar_datos_estaciones()['estaciones']
    index = transmilenio._indice_estaciones(catalog)
    assert transmilenio._resolver_estacion(catalog, 'UNKNOWN-CODE', 'Alcalá', index) is None
    station = transmilenio._resolver_estacion(catalog, 'TM-B-07', 'different label', index)
    assert station['codigo'] == 'TM-B-07'
    normalized = transmilenio._resolver_estacion(
        catalog, '', 'ALCALA' + chr(0x2014) + 'COLEGIO S. TOMAS DOMINICOS', index
    )
    assert normalized['codigo'] == 'TM-B-07'


def test_ambiguous_alias_is_not_resolved():
    catalog = [
        {'id': 'TM-X-01', 'codigo': 'TM-X-01', 'nombre': 'Estación Uno', 'aliases': ['Nombre antiguo']},
        {'id': 'TM-X-02', 'codigo': 'TM-X-02', 'nombre': 'Estación Dos', 'aliases': ['Nombre antiguo']},
    ]
    assert transmilenio._resolver_estacion(catalog, '', 'Nombre antiguo') is None


def test_detail_resolves_old_name_and_keeps_historical_events(isolated_db):
    response = transmilenio.detalle_estacion('Alcalá', usuario={})
    payload = json.loads(response.body)
    assert payload['codigo'] == 'TM-B-07'
    assert payload['estado_operativo'] == 'por_verificar'
    assert len(payload['camaras']) == 4
    assert payload['estadisticas']['total_historico'] == 4
    assert len(payload['eventos_recientes']) == 4


def test_list_filters_keep_station_and_camera_counts(isolated_db):
    payload = json.loads(transmilenio.listar_estaciones(
        troncal='B', con_camaras='true', usuario={}
    ).body)
    assert payload['total'] == 1
    assert payload['estaciones'][0]['codigo'] == 'TM-B-07'


def test_summary_uses_resolved_station_identity(isolated_db):
    response = transmilenio.resumen_global(usuario={})
    payload = json.loads(response.body)
    assert payload['red']['estaciones_cubiertas'] == 1
    assert payload['top_criticas'][0] == {
        'cod_est': 'TM-B-07',
        'nombre': 'Alcalá - Colegio S. Tomás Dominicos',
        'cantidad': 4,
    }


def test_frontend_search_includes_aliases_and_code():
    with open(MAP_VIEW_PATH, encoding='utf-8') as view_file:
        view = view_file.read()
    with open(RENDERER_PATH, encoding='utf-8') as renderer_file:
        renderer = renderer_file.read()
    assert '(e.aliases || []).some(alias =>' in view
    assert '...(apiData.aliases || [])' in renderer


def test_api_preserves_all_operational_states_and_optional_relationships(isolated_db, monkeypatch):
    statuses = [
        'operativa', 'temporal', 'cerrada_temporalmente', 'historica', 'por_verificar'
    ]
    stations = [
        {
            'id': f'TM-X-{index:02d}',
            'codigo': f'TM-X-{index:02d}',
            'nombre': f'Estación de prueba {index}',
            'troncal_id': 'B',
            'troncal': 'Troncal Norte',
            'tipo': 'estacion',
            'estado_operativo': status,
            'aliases': [],
        }
        for index, status in enumerate(statuses, start=1)
    ]
    stations[0]['relaciones'] = [{
        'tipo_relacion': 'reemplaza',
        'codigo_relacionado': 'TM-X-02',
    }]
    monkeypatch.setattr(
        transmilenio,
        '_cargar_datos_estaciones',
        lambda: {'estaciones': stations, 'troncales': []},
    )

    payload = json.loads(transmilenio.listar_estaciones(usuario={}).body)
    assert {station['estado_operativo'] for station in payload['estaciones']} == set(statuses)
    assert payload['estaciones'][0]['relaciones'] == stations[0]['relaciones']


def test_api_keeps_legacy_station_objects_without_optional_metadata(isolated_db, monkeypatch):
    station = {
        'id': 'TM-B-07',
        'codigo': 'TM-B-07',
        'nombre': 'Alcalá - Colegio S. Tomás Dominicos',
        'troncal_id': 'B',
        'troncal': 'Troncal Norte',
        'tipo': 'estacion',
    }
    monkeypatch.setattr(
        transmilenio,
        '_cargar_datos_estaciones',
        lambda: {'estaciones': [station], 'troncales': []},
    )

    payload = json.loads(transmilenio.listar_estaciones(usuario={}).body)
    assert payload['total'] == 1
    assert payload['estaciones'][0]['codigo'] == 'TM-B-07'
    assert 'estado_operativo' not in payload['estaciones'][0]


def test_map_shows_operational_state_without_changing_layout():
    with open(MAP_VIEW_PATH, encoding='utf-8') as view_file:
        view = view_file.read()
    with open(RENDERER_PATH, encoding='utf-8') as renderer_file:
        renderer = renderer_file.read()

    for label in ('operativa', 'temporal', 'cerrada_temporalmente', 'historica', 'por_verificar'):
        assert label in view or label in renderer
    assert 'drawer-estado-operativo' in view
    assert 'Estado' in renderer
    assert 'this._escapeHTML(state)' in renderer


def test_new_station_metadata_and_official_external_ids(isolated_db):
    payload = json.loads(transmilenio.listar_estaciones(usuario={}).body)
    expected = {
        'TM-B-16': ('Calle 187', '02001', 'B'), 'TM-B-17': ('Terminal', '02502', 'B'),
        'TM-D-12': ('Carrera 53', '04105', 'D'), 'TM-D-13': ('Carrera 47', '04106', 'D'),
        'TM-C-13': ('Suba - Calle 116', '03009', 'C'), 'TM-C-14': ('Suba - Calle 95', '03012', 'C'),
        'TM-K-12': ('Quinta Paredes', '06105', 'K'), 'TM-K-13': ('Concejo de Bogotá', '06108', 'K'),
        'TM-K-14': ('Universidades - CityU', '06111', 'K'),
        'TM-E-11': ('La Castellana', '07101', 'E'), 'TM-E-12': ('Calle 75', '07102', 'E'),
        'TM-E-13': ('Movistar Arena', '07105', 'E'), 'TM-E-14': ('Avenida El Dorado', '07108', 'E'),
        'TM-F-16': ('Avenida Américas - Avenida Boyacá', '05102', 'F'),
        'TM-F-17': ('San Facón - Carrera 22', '12004', 'F'), 'TM-F-18': ('Zona Industrial', '12007', 'F'),
        'TM-F-19': ('De la Sabana', '14001', 'F'),
        'TM-H-17': ('Fucha', '09105', 'H'), 'TM-H-18': ('Nariño', '09106', 'H'),
        'TM-H-19': ('Hortúa', '09107', 'H'), 'TM-L-10': ('Bicentenario', '10005', 'L'),
        'TM-M-01': ('Museo Nacional', '10009', 'M'), 'TM-N-01': ('Tygua - San José', '07200', 'N'),
        'TM-G-16': ('Bosa', '07010', 'G'), 'TM-G-17': ('León XIII', '07505', 'G'),
        'TM-G-18': ('La Despensa', '07506', 'G'),
        'TM-Z-01': ('Islandia', '05008', 'Z'), 'TM-Z-02': ('Los Laureles', '05009', 'Z'),
        'TM-Z-03': ('Tibanica - Primavera', '05010', 'Z'),
    }
    found = {item['codigo']: item for item in payload['estaciones']}
    for code, (name, external_id, trunk_id) in expected.items():
        station = found[code]
        assert station['nombre'] == name
        assert station['identificador_oficial_externo'] == external_id
        assert station['troncal_id'] == trunk_id
        assert station['estado_operativo'] == 'operativa'
        assert station['estado_fuente'].startswith('https://')
        assert station['fuente_catalogo_oficial'].startswith('https://')

    trunks = json.loads(transmilenio.listar_troncales(usuario={}).body)['troncales']
    assert {item['id'] for item in trunks} >= {'M', 'N', 'Z'}


def test_new_station_detail_search_and_trunk_filter(isolated_db):
    detail = json.loads(transmilenio.detalle_estacion('TM-Z-03', usuario={}).body)
    assert detail['nombre'] == 'Tibanica - Primavera'
    assert detail['identificador_oficial_externo'] == '05010'
    assert detail['estado_operativo'] == 'operativa'

    catalog = transmilenio._cargar_datos_estaciones()['estaciones']
    index = transmilenio._indice_estaciones(catalog)
    assert transmilenio._resolver_estacion(catalog, '', 'Tibanica - Primavera', index)['codigo'] == 'TM-Z-03'
    assert transmilenio._resolver_estacion(catalog, 'TM-Z-03', '', index)['codigo'] == 'TM-Z-03'

    filtered = json.loads(transmilenio.listar_estaciones(troncal='Z', usuario={}).body)
    assert filtered['total'] == 3
    assert {item['codigo'] for item in filtered['estaciones']} == {'TM-Z-01', 'TM-Z-02', 'TM-Z-03'}


def test_excluded_stations_are_explicitly_missing_from_schematic_layout():
    with open(CATALOG_PATH, encoding='utf-8') as catalog_file:
        catalog = json.load(catalog_file)
    with open(LAYOUT_PATH, encoding='utf-8') as layout_file:
        layout = json.load(layout_file)
    with open(RENDERER_PATH, encoding='utf-8') as renderer_file:
        renderer = renderer_file.read()
    with open(MAP_VIEW_PATH, encoding='utf-8') as view_file:
        view = view_file.read()

    assert {item['codigo'] for item in catalog['estaciones']} - set(layout['stations']) == EXCLUDED_LAYOUT_CODES
    assert 'hasStationPosition(codigo)' in renderer
    assert 'pendiente de representación esquemática' in view
    assert 'openStationDrawer(match.codigo)' in view

