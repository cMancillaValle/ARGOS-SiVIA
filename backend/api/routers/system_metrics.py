"""
api/routers/system_metrics.py
────────────────────────────────────
GET  /api/sistema/metricas   → CPU, RAM, disco, red, GPU
GET  /api/sistema/estado     → Estado resumido del sistema
GET  /api/sistema/ia-config  → Configuración de Athena IA
PUT  /api/sistema/ia-config  → Actualizar configuración de Athena IA
"""

import os
import time
import sqlite3
import threading
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from services.auth_service import get_current_user, require_permission

router = APIRouter()

DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'database', 'argos.db')
)


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_config_table():
    """Crea la tabla configuracion si no existe."""
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


try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    PSUTIL_OK = False

try:
    import subprocess
    subprocess.run(['nvidia-smi'], capture_output=True, timeout=2, check=True)
    NVIDIA_OK = True
except Exception:
    NVIDIA_OK = False


_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 2


def _cached(key: str, fn):
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (now - entry['ts']) < CACHE_TTL:
            return entry['val']
    val = fn()
    with _cache_lock:
        _cache[key] = {'val': val, 'ts': now}
    return val


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
                'nombre':        parts[0] if len(parts) > 0 else '?',
                'temp_c':        int(parts[1]) if len(parts) > 1 else None,
                'uso_pct':       int(parts[2]) if len(parts) > 2 else None,
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


@router.get("/metricas")
def get_metricas(usuario: dict = Depends(require_permission("sistema:ver_estado"))):
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
    return JSONResponse(content=data)


@router.get("/estado")
def get_estado(usuario: dict = Depends(get_current_user)):
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

    return JSONResponse(content=_cached('estado_rapido', _build))


@router.get("/ia-config")
def get_ia_config(usuario: dict = Depends(require_permission("sistema:ver_estado"))):
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
    return JSONResponse(content=result)


@router.put("/ia-config")
async def put_ia_config(request: Request, usuario: dict = Depends(require_permission("sistema:ver_estado"))):
    _ensure_config_table()
    data = await request.json() if await _has_body(request) else {}
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
        return JSONResponse(status_code=500, content={'error': str(e)})

    return JSONResponse(content={'status': 'ok', 'guardadas': guardadas})


async def _has_body(request: Request) -> bool:
    body = await request.body()
    return bool(body)
