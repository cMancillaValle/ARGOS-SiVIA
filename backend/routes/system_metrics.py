"""
routes/system_metrics.py
────────────────────────────────────────────────────────────
GET  /api/sistema/metricas   → CPU, RAM, disco, red, GPU (si está disponible)
GET  /api/sistema/estado     → Estado resumido del sistema (liviano)

Diseño:
  - Usa psutil para recopilar métricas reales del sistema
  - Respuesta JSON ligera, pensada para polling cada 5-10 segundos
  - No bloquea el hilo principal (I/O rápido)
  - Manejo de errores por sección: si GPU falla, responde "no_disponible"
  - Extensible: añadir nuevas métricas sin romper el contrato
"""

import os
import time
import sqlite3
import threading
from datetime import datetime
from flask import Blueprint, jsonify, request
from services.auth_service import requiere_auth, requiere_permiso

DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'database', 'argos.db')
)


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_config_table():
    """Crea la tabla configuracion si no existe (migración mínima)."""
    try:
        conn = _get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL,
                descripcion TEXT,
                actualizado TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()
    except Exception:
        pass

system_metrics_bp = Blueprint('system_metrics', __name__)

# ── Importaciones opcionales ──────────────────────────────────────────────────
try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    import subprocess
    # Intentar nvidia-smi (tarjetas NVIDIA)
    subprocess.run(['nvidia-smi'], capture_output=True, timeout=2, check=True)
    NVIDIA_OK = True
except Exception:
    NVIDIA_OK = False


# ── Cache simple para no sobre-consultar (TTL = 2 segundos) ──────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 2  # segundos


def _cached(key: str, fn):
    """Ejecuta fn() y cachea el resultado por CACHE_TTL segundos."""
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (now - entry['ts']) < CACHE_TTL:
            return entry['val']
    val = fn()
    with _cache_lock:
        _cache[key] = {'val': val, 'ts': now}
    return val


# ── Helpers de métricas ────────────────────────────────────────────────────────

def _get_cpu():
    if not PSUTIL_OK:
        return {'disponible': False, 'razon': 'psutil no instalado'}
    try:
        return {
            'disponible': True,
            'uso_pct':    psutil.cpu_percent(interval=0.5),
            'nucleos':    psutil.cpu_count(logical=False),
            'hilos':      psutil.cpu_count(logical=True),
            'frecuencia': round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else None,
            'carga_1m':   round(psutil.getloadavg()[0], 2) if hasattr(psutil, 'getloadavg') else None,
        }
    except Exception as e:
        return {'disponible': False, 'razon': str(e)}


def _get_ram():
    if not PSUTIL_OK:
        return {'disponible': False, 'razon': 'psutil no instalado'}
    try:
        m = psutil.virtual_memory()
        return {
            'disponible':  True,
            'total_gb':    round(m.total / 1e9, 2),
            'usado_gb':    round(m.used  / 1e9, 2),
            'libre_gb':    round(m.available / 1e9, 2),
            'uso_pct':     m.percent,
        }
    except Exception as e:
        return {'disponible': False, 'razon': str(e)}


def _get_disco():
    if not PSUTIL_OK:
        return {'disponible': False, 'razon': 'psutil no instalado'}
    try:
        # Disco del directorio del proyecto
        base = os.path.dirname(os.path.abspath(__file__))
        d = psutil.disk_usage(base)
        io = psutil.disk_io_counters() if hasattr(psutil, 'disk_io_counters') else None
        return {
            'disponible': True,
            'total_gb':   round(d.total / 1e9, 2),
            'usado_gb':   round(d.used  / 1e9, 2),
            'libre_gb':   round(d.free  / 1e9, 2),
            'uso_pct':    d.percent,
            'lectura_mb': round(io.read_bytes  / 1e6, 1) if io else None,
            'escritura_mb': round(io.write_bytes / 1e6, 1) if io else None,
        }
    except Exception as e:
        return {'disponible': False, 'razon': str(e)}


def _get_red():
    if not PSUTIL_OK:
        return {'disponible': False, 'razon': 'psutil no instalado'}
    try:
        net = psutil.net_io_counters()
        conns = len(psutil.net_connections(kind='inet')) if hasattr(psutil, 'net_connections') else None
        return {
            'disponible':        True,
            'bytes_enviados_mb': round(net.bytes_sent    / 1e6, 2),
            'bytes_recibidos_mb': round(net.bytes_recv   / 1e6, 2),
            'paquetes_enviados': net.packets_sent,
            'paquetes_recibidos': net.packets_recv,
            'errores_salida':    net.errout,
            'errores_entrada':   net.errin,
            'conexiones_activas': conns,
        }
    except Exception as e:
        return {'disponible': False, 'razon': str(e)}


def _get_procesos():
    if not PSUTIL_OK:
        return {'disponible': False, 'razon': 'psutil no instalado'}
    try:
        procs = []
        # Los 5 procesos que más RAM consumen
        for p in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
                        key=lambda x: x.info.get('memory_percent') or 0,
                        reverse=True)[:5]:
            try:
                procs.append({
                    'pid':        p.info['pid'],
                    'nombre':     p.info['name'],
                    'cpu_pct':    round(p.info['cpu_percent'] or 0, 1),
                    'ram_pct':    round(p.info['memory_percent'] or 0, 1),
                })
            except Exception:
                pass
        return {
            'disponible': True,
            'total':      len(psutil.pids()),
            'top_5':      procs,
        }
    except Exception as e:
        return {'disponible': False, 'razon': str(e)}


def _get_gpu():
    """Lee GPU NVIDIA via nvidia-smi. Devuelve info o no_disponible."""
    if not NVIDIA_OK:
        return {'disponible': False, 'razon': 'nvidia-smi no detectado'}
    try:
        import subprocess
        out = subprocess.run(
            ['nvidia-smi',
             '--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=3
        )
        if out.returncode != 0:
            return {'disponible': False, 'razon': 'nvidia-smi error'}
        lines = [l.strip() for l in out.stdout.strip().split('\n') if l.strip()]
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(',')]
            gpus.append({
                'nombre':      parts[0] if len(parts) > 0 else '?',
                'temp_c':      int(parts[1]) if len(parts) > 1 else None,
                'uso_pct':     int(parts[2]) if len(parts) > 2 else None,
                'vram_usada_mb': int(parts[3]) if len(parts) > 3 else None,
                'vram_total_mb': int(parts[4]) if len(parts) > 4 else None,
            })
        return {'disponible': True, 'gpus': gpus}
    except Exception as e:
        return {'disponible': False, 'razon': str(e)}


def _get_uptime():
    if not PSUTIL_OK:
        return None
    try:
        boot = psutil.boot_time()
        up_s = int(time.time() - boot)
        h, rem = divmod(up_s, 3600)
        m, s   = divmod(rem, 60)
        return f"{h}h {m}m {s}s"
    except Exception:
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@system_metrics_bp.route('/metricas', methods=['GET'])
@requiere_auth
@requiere_permiso('sistema:ver_estado')
def get_metricas():
    """
    Métricas completas del sistema.
    Responde en < 600ms gracias al cache de 2 segundos.
    """
    data = _cached('metricas_completas', lambda: {
        'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'uptime':    _get_uptime(),
        'cpu':       _get_cpu(),
        'ram':       _get_ram(),
        'disco':     _get_disco(),
        'red':       _get_red(),
        'gpu':       _get_gpu(),
        'procesos':  _get_procesos(),
        'psutil_ok': PSUTIL_OK,
    })
    return jsonify(data)


@system_metrics_bp.route('/estado', methods=['GET'])
@requiere_auth
def get_estado():
    """
    Estado rápido (para el topbar / badge del dashboard).
    Solo CPU y RAM. Responde en < 200ms.
    """
    def _build():
        estado = {'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}
        if PSUTIL_OK:
            try:
                estado['cpu_pct'] = psutil.cpu_percent(interval=0.1)
                estado['ram_pct'] = psutil.virtual_memory().percent
            except Exception:
                estado['cpu_pct'] = None
                estado['ram_pct'] = None
        else:
            estado['cpu_pct'] = None
            estado['ram_pct'] = None
            estado['advertencia'] = 'Instalar psutil: pip install psutil'
        return estado

    return jsonify(_cached('estado_rapido', _build))


# ── Configuración IA ──────────────────────────────────────────────────────────

@system_metrics_bp.route('/ia-config', methods=['GET'])
@requiere_auth
@requiere_permiso('sistema:ver_estado')
def get_ia_config():
    """
    Lee la configuración del motor IA (umbral de confianza, etc.).
    GET /api/sistema/ia-config
    """
    _ensure_config_table()
    defaults = {
        'ia_confidence_threshold': '0.50',
        'ia_inference_interval_ms': '500',
        'ia_model': 'yolov8n',
        'ia_gpu_enabled': 'true',
    }
    result = {}
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT clave, valor FROM configuracion WHERE clave LIKE 'ia_%'"
        ).fetchall()
        conn.close()
        stored = {r['clave']: r['valor'] for r in rows}
        for k, v in defaults.items():
            result[k] = stored.get(k, v)
    except Exception as e:
        result = dict(defaults)
        result['error'] = str(e)
    return jsonify(result)


@system_metrics_bp.route('/ia-config', methods=['PUT'])
@requiere_auth
@requiere_permiso('sistema:ver_estado')
def put_ia_config():
    """
    Guarda configuración del motor IA.
    PUT /api/sistema/ia-config
    Body JSON: { "ia_confidence_threshold": 0.80, ... }
    """
    _ensure_config_table()
    data = request.get_json(silent=True) or {}
    claves_permitidas = {
        'ia_confidence_threshold', 'ia_inference_interval_ms',
        'ia_model', 'ia_gpu_enabled',
    }
    guardadas = []
    try:
        conn = _get_conn()
        for clave, valor in data.items():
            if clave not in claves_permitidas:
                continue
            conn.execute("""
                INSERT INTO configuracion (clave, valor, actualizado)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(clave) DO UPDATE SET
                    valor = excluded.valor,
                    actualizado = excluded.actualizado
            """, (clave, str(valor)))
            guardadas.append(clave)
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'status': 'ok', 'guardadas': guardadas})
