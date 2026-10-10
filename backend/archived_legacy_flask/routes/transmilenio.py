"""
ARGOS - SiViA · Módulo de Integración TransMilenio
────────────────────────────────────────────────────
Provee endpoints para el mapa interactivo georreferenciado:
- Listado de estaciones y trazados de troncales
- Enlace en tiempo real con cámaras y eventos de evasión de ARGOS
- Estadísticas e indicadores de riesgo por estación
"""

import os
import json
import sqlite3
from datetime import datetime, date
from flask import Blueprint, jsonify, request, current_app
from services.auth_service import requiere_auth

transmilenio_bp = Blueprint('transmilenio_bp', __name__)

DATA_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'estaciones_transmilenio.json')
)


def _get_db():
    db_path = current_app.config.get('DB_PATH')
    if not db_path:
        db_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'argos.db')
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _cargar_datos_estaciones():
    """Carga el catálogo de estaciones y troncales desde el archivo local JSON."""
    if not os.path.exists(DATA_FILE):
        return {'troncales': [], 'estaciones': []}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[TransMilenio] Error cargando {DATA_FILE}: {e}")
        return {'troncales': [], 'estaciones': []}


@transmilenio_bp.route('/estaciones', methods=['GET'])
@requiere_auth
def listar_estaciones():
    catalogo = _cargar_datos_estaciones()
    estaciones = catalogo.get('estaciones', [])
    troncal_filtro = request.args.get('troncal', '').strip().upper()
    solo_monitoreadas = request.args.get('con_camaras', 'false').lower() == 'true'

    conn = _get_db()
    cursor = conn.cursor()

    hoy_str = date.today().strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT 
            COALESCE(codigo_estacion, '') as cod_est,
            LOWER(estacion) as nombre_norm,
            COUNT(*) as total_camaras,
            SUM(CASE WHEN estado = 'activa' THEN 1 ELSE 0 END) as camaras_activas,
            SUM(CASE WHEN estado = 'offline' THEN 1 ELSE 0 END) as camaras_offline,
            SUM(CASE WHEN estado = 'mantenimiento' THEN 1 ELSE 0 END) as camaras_mant
        FROM camaras
        GROUP BY codigo_estacion, LOWER(estacion)
    """)
    camaras_rows = cursor.fetchall()
    
    cam_por_codigo = {}
    cam_por_nombre = {}
    for r in camaras_rows:
        info = {
            'total': r['total_camaras'],
            'activas': r['camaras_activas'] or 0,
            'offline': r['camaras_offline'] or 0,
            'mantenimiento': r['camaras_mant'] or 0
        }
        if r['cod_est']:
            cam_por_codigo[r['cod_est'].upper()] = info
        cam_por_nombre[r['nombre_norm']] = info

    cursor.execute("""
        SELECT 
            COALESCE(c.codigo_estacion, '') as cod_est,
            LOWER(c.estacion) as nombre_norm,
            COUNT(e.id) as total_evasiones_hoy,
            SUM(CASE WHEN e.estado = 'confirmado' THEN 1 ELSE 0 END) as confirmadas_hoy,
            SUM(CASE WHEN e.estado = 'pendiente' THEN 1 ELSE 0 END) as pendientes_hoy,
            MAX(e.detectado_en) as ultima_deteccion
        FROM eventos e
        JOIN camaras c ON e.camara_id = c.id
        WHERE DATE(e.detectado_en) = ?
        GROUP BY c.codigo_estacion, LOWER(c.estacion)
    """, (hoy_str,))
    ev_rows = cursor.fetchall()

    ev_por_codigo = {}
    ev_por_nombre = {}
    for r in ev_rows:
        info = {
            'total_hoy': r['total_evasiones_hoy'],
            'confirmadas': r['confirmadas_hoy'] or 0,
            'pendientes': r['pendientes_hoy'] or 0,
            'ultima_deteccion': r['ultima_deteccion']
        }
        if r['cod_est']:
            ev_por_codigo[r['cod_est'].upper()] = info
        ev_por_nombre[r['nombre_norm']] = info

    conn.close()

    resultado = []
    for est in estaciones:
        cod = est.get('codigo', '').upper()
        nom_norm = est.get('nombre', '').strip().lower()

        if troncal_filtro and est.get('troncal_id', '').upper() != troncal_filtro:
            continue

        cam_info = cam_por_codigo.get(cod) or cam_por_nombre.get(nom_norm) or {
            'total': 0, 'activas': 0, 'offline': 0, 'mantenimiento': 0
        }

        if solo_monitoreadas and cam_info['total'] == 0:
            continue

        ev_info = ev_por_codigo.get(cod) or ev_por_nombre.get(nom_norm) or {
            'total_hoy': 0, 'confirmadas': 0, 'pendientes': 0, 'ultima_deteccion': None
        }

        total_ev = ev_info['total_hoy']
        if total_ev >= 6:
            riesgo = 'critico'
        elif total_ev >= 2:
            riesgo = 'alerta'
        else:
            riesgo = 'normal'

        est_enriquecida = dict(est)
        est_enriquecida['camaras'] = cam_info
        est_enriquecida['eventos_hoy'] = ev_info
        est_enriquecida['riesgo'] = riesgo
        est_enriquecida['monitoreada'] = cam_info['total'] > 0

        resultado.append(est_enriquecida)

    return jsonify({
        'total': len(resultado),
        'fecha': hoy_str,
        'estaciones': resultado
    })


@transmilenio_bp.route('/estaciones/<id_o_codigo>', methods=['GET'])
@requiere_auth
def detalle_estacion(id_o_codigo):
    catalogo = _cargar_datos_estaciones()
    estaciones = catalogo.get('estaciones', [])
    id_o_codigo_clean = str(id_o_codigo).strip().upper()

    estacion_match = None
    for est in estaciones:
        if est.get('id', '').upper() == id_o_codigo_clean or est.get('codigo', '').upper() == id_o_codigo_clean:
            estacion_match = dict(est)
            break
        if est.get('nombre', '').strip().upper() == id_o_codigo_clean:
            estacion_match = dict(est)
            break

    if not estacion_match:
        return jsonify({'error': f'Estación "{id_o_codigo}" no encontrada en el catálogo'}), 404

    conn = _get_db()
    cursor = conn.cursor()
    cod_est = estacion_match.get('codigo', '')
    nom_est = estacion_match.get('nombre', '')

    cursor.execute("""
        SELECT id, codigo, ubicacion, estado, ip, fps, resolucion, instalada
        FROM camaras
        WHERE UPPER(codigo_estacion) = ? OR UPPER(estacion) = ?
        ORDER BY codigo ASC
    """, (cod_est.upper(), nom_est.upper()))
    camaras = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
        SELECT 
            e.id, e.camara_id, e.tipo, e.confianza, e.estado, e.observaciones, 
            e.detectado_en, c.codigo as camara_codigo, c.ubicacion as camara_ubicacion,
            u.nombre as operador_nombre
        FROM eventos e
        JOIN camaras c ON e.camara_id = c.id
        LEFT JOIN usuarios u ON e.operador_id = u.id
        WHERE UPPER(c.codigo_estacion) = ? OR UPPER(c.estacion) = ?
        ORDER BY e.detectado_en DESC
        LIMIT 10
    """, (cod_est.upper(), nom_est.upper()))
    eventos_recientes = [dict(r) for r in cursor.fetchall()]

    hoy_str = date.today().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT 
            COUNT(e.id) as total_historico,
            SUM(CASE WHEN DATE(e.detectado_en) = ? THEN 1 ELSE 0 END) as hoy_total,
            SUM(CASE WHEN DATE(e.detectado_en) = ? AND e.estado = 'confirmado' THEN 1 ELSE 0 END) as hoy_confirmadas,
            SUM(CASE WHEN DATE(e.detectado_en) = ? AND e.estado = 'pendiente' THEN 1 ELSE 0 END) as hoy_pendientes
        FROM eventos e
        JOIN camaras c ON e.camara_id = c.id
        WHERE UPPER(c.codigo_estacion) = ? OR UPPER(c.estacion) = ?
    """, (hoy_str, hoy_str, hoy_str, cod_est.upper(), nom_est.upper()))
    stats_row = cursor.fetchone()

    stats = {
        'total_historico': stats_row['total_historico'] or 0,
        'hoy_total': stats_row['hoy_total'] or 0,
        'hoy_confirmadas': stats_row['hoy_confirmadas'] or 0,
        'hoy_pendientes': stats_row['hoy_pendientes'] or 0
    }

    conn.close()

    estacion_match['camaras'] = camaras
    estacion_match['eventos_recientes'] = eventos_recientes
    estacion_match['estadisticas'] = stats

    return jsonify(estacion_match)


@transmilenio_bp.route('/troncales', methods=['GET'])
@requiere_auth
def listar_troncales():
    catalogo = _cargar_datos_estaciones()
    troncales = catalogo.get('troncales', [])
    return jsonify({'troncales': troncales})


@transmilenio_bp.route('/resumen', methods=['GET'])
@requiere_auth
def resumen_global():
    catalogo = _cargar_datos_estaciones()
    total_estaciones_red = len(catalogo.get('estaciones', []))

    conn = _get_db()
    cursor = conn.cursor()
    hoy_str = date.today().strftime('%Y-%m-%d')

    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN estado = 'activa' THEN 1 ELSE 0 END) as activas,
            SUM(CASE WHEN estado = 'offline' THEN 1 ELSE 0 END) as offline,
            COUNT(DISTINCT COALESCE(codigo_estacion, estacion)) as estaciones_cubiertas
        FROM camaras
    """)
    cam_stats = cursor.fetchone()

    cursor.execute("""
        SELECT 
            COUNT(*) as total_hoy,
            SUM(CASE WHEN estado = 'confirmado' THEN 1 ELSE 0 END) as confirmados,
            SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) as pendientes
        FROM eventos
        WHERE DATE(detectado_en) = ?
    """, (hoy_str,))
    ev_stats = cursor.fetchone()

    cursor.execute("""
        SELECT 
            COALESCE(c.codigo_estacion, '') as cod_est,
            c.estacion as nombre,
            COUNT(e.id) as cantidad
        FROM eventos e
        JOIN camaras c ON e.camara_id = c.id
        WHERE DATE(e.detectado_en) = ?
        GROUP BY c.codigo_estacion, c.estacion
        ORDER BY cantidad DESC
        LIMIT 3
    """, (hoy_str,))
    top_estaciones = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return jsonify({
        'red': {
            'total_estaciones': total_estaciones_red,
            'estaciones_cubiertas': cam_stats['estaciones_cubiertas'] or 0,
            'cobertura_pct': round(((cam_stats['estaciones_cubiertas'] or 0) / max(total_estaciones_red, 1)) * 100, 1)
        },
        'camaras': {
            'total': cam_stats['total'] or 0,
            'activas': cam_stats['activas'] or 0,
            'offline': cam_stats['offline'] or 0
        },
        'evasiones_hoy': {
            'total': ev_stats['total_hoy'] or 0,
            'confirmadas': ev_stats['confirmados'] or 0,
            'pendientes': ev_stats['pendientes'] or 0
        },
        'top_criticas': top_estaciones
    })
