"""
database/db.py
──────────────
Inicialización de SQLite y datos semilla para ARGOS - SiViA.
Usa solo la librería estándar (sqlite3 + hashlib).
"""

import sqlite3
import hashlib
import os
from datetime import datetime, timedelta
import random


# ══════════════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════════════

from werkzeug.security import generate_password_hash
def hash_password(plain: str) -> str:
    """Utiliza werkzeug (PBKDF2/scrypt) en reemplazo del antiguo SHA-256."""
    return generate_password_hash(plain)


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row          # devuelve dicts
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


# ══════════════════════════════════════════════════════
#  ESQUEMA
# ══════════════════════════════════════════════════════

SCHEMA = """
-- Usuarios del sistema
CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    password    TEXT    NOT NULL,
    nombre      TEXT    NOT NULL,
    email       TEXT    NOT NULL,
    rol         TEXT    NOT NULL CHECK(rol IN ('admin','supervisor','operador','analista','tecnico','auditor')),
    activo      INTEGER NOT NULL DEFAULT 1,
    creado_en   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Sesiones activas (tokens simples)
CREATE TABLE IF NOT EXISTS sesiones (
    token       TEXT    PRIMARY KEY,
    usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
    creado_en   TEXT    NOT NULL DEFAULT (datetime('now')),
    expira_en   TEXT    NOT NULL
);

-- Cámaras instaladas en estaciones
CREATE TABLE IF NOT EXISTS camaras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT    NOT NULL UNIQUE,        -- ej. CAM-001
    estacion    TEXT    NOT NULL,               -- ej. Portal Norte
    ubicacion   TEXT    NOT NULL,               -- ej. Torniquete 3 - Entrada A
    estado      TEXT    NOT NULL DEFAULT 'activa'
                        CHECK(estado IN ('activa','offline','mantenimiento')),
    ip          TEXT,
    fps         INTEGER NOT NULL DEFAULT 15,
    resolucion  TEXT    NOT NULL DEFAULT '1080p',
    instalada   TEXT    NOT NULL DEFAULT (date('now'))
);

-- Eventos de evasión detectados por la IA
CREATE TABLE IF NOT EXISTS eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    camara_id       INTEGER NOT NULL REFERENCES camaras(id),
    tipo            TEXT    NOT NULL DEFAULT 'evasion'
                            CHECK(tipo IN ('evasion','intrusion','caida','otro')),
    confianza       REAL    NOT NULL,           -- 0.0 - 1.0
    estado          TEXT    NOT NULL DEFAULT 'pendiente'
                            CHECK(estado IN ('pendiente','confirmado','descartado')),
    observaciones   TEXT,
    operador_id     INTEGER REFERENCES usuarios(id),
    detectado_en    TEXT    NOT NULL DEFAULT (datetime('now')),
    revisado_en     TEXT
);

-- Log de acciones de auditoría
CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER REFERENCES usuarios(id),
    accion      TEXT    NOT NULL,
    detalle     TEXT,
    ip_origen   TEXT,
    fecha       TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Configuración global del sistema
CREATE TABLE IF NOT EXISTS configuracion (
    clave       TEXT PRIMARY KEY,
    valor       TEXT NOT NULL,
    descripcion TEXT,
    actualizado TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ══════════════════════════════════════════════════════
#  INICIALIZAR BD
# ══════════════════════════════════════════════════════

def init_db(db_path: str):
    """Crea las tablas si no existen."""
    conn = get_conn(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f'[DB] Base de datos inicializada: {db_path}')


# ══════════════════════════════════════════════════════
#  DATOS SEMILLA
# ══════════════════════════════════════════════════════

USUARIOS_DEMO = [
    ('admin',      'admin123',  'Administrador ARGOS',      'admin@transmilenio.gov.co',      'admin'),
    ('supervisor', 'sup123',    'Ana Martínez',              'a.martinez@transmilenio.gov.co', 'supervisor'),
    ('operador',   'op123',     'Carlos Rodríguez',          'c.rodriguez@transmilenio.gov.co','operador'),
    ('analista',   'an123',     'Diana Pérez',               'd.perez@transmilenio.gov.co',    'analista'),
    ('tecnico',    'tec123',    'Eduardo Gómez',             'e.gomez@transmilenio.gov.co',    'tecnico'),
    ('auditor',    'aud123',    'Fernanda Torres',           'f.torres@transmilenio.gov.co',   'auditor'),
]

CAMARAS_DEMO = [
    ('CAM-001','Portal Norte',   'Torniquete 1 - Entrada Principal',  'activa',        '192.168.1.101'),
    ('CAM-002','Portal Norte',   'Torniquete 2 - Entrada Principal',  'activa',        '192.168.1.102'),
    ('CAM-003','Portal Norte',   'Torniquete 3 - Salida',             'activa',        '192.168.1.103'),
    ('CAM-004','Portal Norte',   'Torniquete 4 - Salida',             'activa',        '192.168.1.104'),
    ('CAM-005','Portal Norte',   'Acceso Bicicarril',                 'mantenimiento', '192.168.1.105'),
    ('CAM-006','Portal Sur',     'Torniquete 1 - Entrada A',          'activa',        '192.168.1.201'),
    ('CAM-007','Portal Sur',     'Torniquete 2 - Entrada A',          'activa',        '192.168.1.202'),
    ('CAM-008','Portal Sur',     'Torniquete 1 - Entrada B',          'activa',        '192.168.1.203'),
    ('CAM-009','Portal Sur',     'Pasillo Central',                   'offline',       '192.168.1.204'),
    ('CAM-010','Portal 80',      'Torniquete 1',                      'activa',        '192.168.1.301'),
    ('CAM-011','Portal 80',      'Torniquete 2',                      'activa',        '192.168.1.302'),
    ('CAM-012','Portal 80',      'Torniquete 3',                      'activa',        '192.168.1.303'),
    ('CAM-013','Portal El Dorado','Torniquete 1 - Acceso Metro',      'activa',        '192.168.1.401'),
    ('CAM-014','Portal El Dorado','Torniquete 2 - Acceso Metro',      'activa',        '192.168.1.402'),
    ('CAM-015','Calle 100',      'Torniquete 1',                      'activa',        '192.168.1.501'),
    ('CAM-016','Calle 100',      'Torniquete 2',                      'activa',        '192.168.1.502'),
    ('CAM-017','Calle 72',       'Torniquete 1',                      'activa',        '192.168.1.601'),
    ('CAM-018','Calle 72',       'Torniquete 2',                      'activa',        '192.168.1.602'),
    ('CAM-019','Av. Jiménez',    'Torniquete 1',                      'activa',        '192.168.1.701'),
    ('CAM-020','Av. Jiménez',    'Torniquete 2',                      'activa',        '192.168.1.702'),
]


def seed_db(db_path: str):
    """Inserta datos demo si las tablas están vacías."""
    conn = get_conn(db_path)

    # Usuarios
    existing = conn.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]
    if existing == 0:
        for username, password, nombre, email, rol in USUARIOS_DEMO:
            conn.execute(
                'INSERT INTO usuarios (username, password, nombre, email, rol) VALUES (?,?,?,?,?)',
                (username, hash_password(password), nombre, email, rol)
            )
        print(f'[DB] {len(USUARIOS_DEMO)} usuarios demo insertados')

    # Cámaras
    existing = conn.execute('SELECT COUNT(*) FROM camaras').fetchone()[0]
    if existing == 0:
        for codigo, estacion, ubicacion, estado, ip in CAMARAS_DEMO:
            conn.execute(
                'INSERT INTO camaras (codigo, estacion, ubicacion, estado, ip) VALUES (?,?,?,?,?)',
                (codigo, estacion, ubicacion, estado, ip)
            )
        print(f'[DB] {len(CAMARAS_DEMO)} cámaras demo insertadas')

    # Eventos simulados (últimas 48 horas)
    existing = conn.execute('SELECT COUNT(*) FROM eventos').fetchone()[0]
    if existing == 0:
        tipos     = ['evasion', 'evasion', 'evasion', 'intrusion', 'otro']
        estados   = ['confirmado', 'confirmado', 'descartado', 'pendiente']
        ahora     = datetime.now()
        eventos   = []
        for i in range(60):
            cam_id    = random.randint(1, len(CAMARAS_DEMO))
            tipo      = random.choice(tipos)
            confianza = round(random.uniform(0.65, 0.99), 2)
            estado    = random.choice(estados)
            delta     = timedelta(hours=random.uniform(0, 48))
            detectado = (ahora - delta).strftime('%Y-%m-%d %H:%M:%S')
            op_id     = random.choice([None, 3])   # operador o sin asignar
            eventos.append((cam_id, tipo, confianza, estado, op_id, detectado))

        conn.executemany(
            'INSERT INTO eventos (camara_id, tipo, confianza, estado, operador_id, detectado_en) VALUES (?,?,?,?,?,?)',
            eventos
        )
        print(f'[DB] 60 eventos demo insertados')

    # Configuración IA (valores por defecto si no existe)
    ia_existing = conn.execute(
        "SELECT COUNT(*) FROM configuracion WHERE clave LIKE 'ia_%'"
    ).fetchone()[0]
    if ia_existing == 0:
        defaults_ia = [
            ('ia_confidence_threshold',  '0.50', 'Umbral de confianza mínima YOLO (0.0-1.0)'),
            ('ia_inference_interval_ms', '500',  'Intervalo de inferencia en milisegundos'),
            ('ia_model',                 'yolov8n', 'Modelo YOLOv8 activo'),
            ('ia_gpu_enabled',           'true', 'Usar GPU CUDA si está disponible'),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO configuracion (clave, valor, descripcion) VALUES (?,?,?)",
            defaults_ia
        )
        print('[DB] Configuración IA por defecto insertada')

    conn.commit()
    conn.close()

