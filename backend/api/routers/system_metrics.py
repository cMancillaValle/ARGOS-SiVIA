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
    conn.execute('PRAGMA foreign_keys = ON')
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
async def put_ia_config(request: Request, usuario: dict = Depends(require_permission("configuracion:ia"))):
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



# ── GET /api/sistema/config (F30) ─────────────────────────────────
@router.get("/config")
def get_sistema_config(usuario: dict = Depends(require_permission("configuracion:ver"))):
    """
    Retorna la configuración general del sistema.
    Requiere permiso 'configuracion:ver' (Admin y Técnico).
    """
    _ensure_config_table()
    defaults = {
        'timezone': 'America/Bogota',
        'modo': 'produccion',
        'debug': 'false',
        'ret_eventos': '90',
        'ret_audit': '365',
        'ret_snap': '30',
        'autoclean': 'true',
        'session_ttl': '480',
        'max_fail': '5',
        'lockout_min': '15',
        'fa2_force': 'true',
        'log_ip': 'true',
        'maintenance': 'false',
        'nombre_sistema': 'ARGOS SiViA - TransMilenio',
    }
    result = {}
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT clave, valor FROM configuracion WHERE clave NOT LIKE 'ia_%'").fetchall()
        conn.close()
        stored = {r['clave']: r['valor'] for r in rows}
        for k, v in defaults.items():
            result[k] = stored.get(k, v)
    except Exception as e:
        result = dict(defaults)
        result['error'] = str(e)
    return JSONResponse(content=result)


# ── PUT /api/sistema/config (F30) ─────────────────────────────────
@router.put("/config")
async def put_sistema_config(
    request: Request,
    usuario: dict = Depends(require_permission("configuracion:editar"))
):
    """
    Guarda y persiste las variables de configuración general del sistema.
    Requiere permiso 'configuracion:editar' (Admin).
    """
    _ensure_config_table()
    data = await request.json() if await _has_body(request) else {}
    if not isinstance(data, dict):
        return JSONResponse(status_code=400, content={'error': 'El cuerpo debe ser un objeto JSON.'})

    claves_permitidas = {
        'timezone', 'modo', 'debug', 'ret_eventos', 'ret_audit',
        'ret_snap', 'autoclean', 'session_ttl', 'max_fail',
        'lockout_min', 'fa2_force', 'log_ip', 'maintenance',
        'nombre_sistema'
    }

    # Validaciones básicas de rangos
    if 'session_ttl' in data:
        try:
            ttl_val = int(data['session_ttl'])
            if ttl_val < 30 or ttl_val > 1440:
                return JSONResponse(status_code=400, content={'error': 'session_ttl debe estar entre 30 y 1440 minutos.'})
        except (ValueError, TypeError):
            return JSONResponse(status_code=400, content={'error': 'session_ttl inválido.'})

    if 'max_fail' in data:
        try:
            mf = int(data['max_fail'])
            if mf < 3 or mf > 20:
                return JSONResponse(status_code=400, content={'error': 'max_fail debe estar entre 3 y 20 intentos.'})
        except (ValueError, TypeError):
            return JSONResponse(status_code=400, content={'error': 'max_fail inválido.'})

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


# ── POST /api/sistema/test-smtp (F30) ────────────────────────────────
@router.post("/test-smtp")
def post_test_smtp(usuario: dict = Depends(require_permission("configuracion:editar"))):
    """
    Verifica de manera real y segura la conectividad y configuración del transporte SMTP
    utilizando las credenciales configuradas en las variables de entorno del servidor.
    No expone secretos, contraseñas ni tokens.
    Requiere permiso administrativo 'configuracion:editar'.
    """
    import smtplib
    import ssl

    host = os.environ.get('SMTP_HOST', '').strip() or 'smtp.gmail.com'
    port_str = os.environ.get('SMTP_PORT', '587').strip()
    try:
        port = int(port_str)
    except ValueError:
        port = 587

    user = os.environ.get('SMTP_USER', '').strip()
    password = os.environ.get('SMTP_PASS', '').strip()

    if not user or not password:
        return JSONResponse(status_code=400, content={
            'status': 'error',
            'error': 'Servicio SMTP no configurado: faltan variables SMTP_USER / SMTP_PASS en el servidor.'
        })

    # Probar conexión y handshake real con timeout estricto de 5s
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=5) as server:
            server.ehlo()
            if port == 587:
                server.starttls(context=ctx)
                server.ehlo()
            server.login(user, password)

        return JSONResponse(content={
            'status': 'ok',
            'mensaje': f'Conexión y autenticación SMTP exitosa con {host}:{port}'
        })
    except smtplib.SMTPAuthenticationError:
        return JSONResponse(status_code=401, content={
            'status': 'error',
            'error': f'Fallo de autenticación con el servidor SMTP ({host}:{port}). Verifique usuario y clave.'
        })
    except (smtplib.SMTPConnectError, ConnectionRefusedError, OSError) as e:
        return JSONResponse(status_code=502, content={
            'status': 'error',
            'error': f'No se pudo conectar al host SMTP {host}:{port}.'
        })
    except TimeoutError:
        return JSONResponse(status_code=504, content={
            'status': 'error',
            'error': f'Tiempo de espera agotado al conectar a {host}:{port} (>5s).'
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            'status': 'error',
            'error': f'Error durante la verificación SMTP: {type(e).__name__}'
        })