/**
 * frontend/js/transmilenio-schematic-map.js
 * ────────────────────────────────────────────────────────────
 * ARGOS SiViA · Renderizador SVG Esquemático Interactivo
 * Basado fielmente en la topología de la red de TransMilenio (mapaTM).
 *
 * Principios:
 * - 100% libre de Leaflet, tiles remotos y coordenadas GPS.
 * - Renderizado accesible mediante DOM createElementNS (cero innerHTML inseguro).
 * - Pan & Zoom nativo con aceleración por matriz y controles interactivos.
 * - Adaptación automática a temas Claro y Oscuro de ARGOS.
 * - Diferenciación visual no solo por color (formas, halos, anillos, pulsos).
 * - Tooltip interactivo flotante y navegación hacia drawer operativo.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.TransmilenioSchematicMap = factory();
  }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  const ESTADOS_OPERATIVOS_LABELS = {
    operativa: 'Operativa',
    temporal: 'Temporal en operación',
    cerrada_temporalmente: 'Cerrada temporalmente',
    historica: 'Histórica',
    por_verificar: 'Por verificar'
  };

  function normalizarBusqueda(valor) {
    return String(valor || '')
      .normalize('NFKD')
      .replace(/[\u2010-\u2015\u2212]/g, '-')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\s*-\s*/g, ' - ')
      .trim()
      .replace(/\s+/g, ' ')
      .toLocaleLowerCase();
  }

  class TransmilenioSchematicMap {
    /**
     * @param {Object} options
     * @param {HTMLElement} options.container - Elemento contenedor
     * @param {Object} options.layout - TRANSMILENIO_LAYOUT
     * @param {Array} options.estaciones - Array de estaciones desde /api/transmilenio/estaciones
     * @param {Array} options.troncales - Array de troncales desde /api/transmilenio/troncales
     * @param {Function} [options.onSelectStation] - Callback al seleccionar estación
     */
    constructor(options) {
      if (!options || !options.container) {
        throw new Error('[SchematicMap] Se requiere un contenedor válido');
      }

      this.container = options.container;
      this.layout = options.layout || (typeof TRANSMILENIO_LAYOUT !== 'undefined' ? TRANSMILENIO_LAYOUT : null);
      this.estacionesData = options.estaciones || [];
      this.troncalesData = options.troncales || [];
      this.onSelectStation = options.onSelectStation || (() => {});

      // Mapa indexado de estaciones de la API
      this.estacionesMap = new Map();
      this.troncalesMap = new Map();

      // Estado de visualización
      this.estacionSeleccionada = null;
      this.troncalFiltro = '';
      this.filtroEstado = 'todos'; // 'todos' | 'con_camaras' | 'con_evasiones'
      this.busqueda = '';

      // Pan & Zoom
      this.scale = 1;
      this.panX = 0;
      this.panY = 0;
      this.isPanning = false;
      this._mousePanStart = null;

      // Elementos SVG
      this.svg = null;
      this.viewportGroup = null;
      this.corridorsGroup = null;
      this.connectionsGroup = null;
      this.stationsGroup = null;
      this.tooltip = null;
      this.hoveredCode = null;
      this.hoveredNode = null;
      this.inputMode = 'mouse';

      this._init();
    }

    _init() {
      this._indexData();
      this._createDOM();
      this._bindEvents();
      this.render();
      this.resetView();
    }

    _indexData() {
      this.estacionesMap.clear();
      this.troncalesMap.clear();

      (this.estacionesData || []).forEach(est => {
        const cod = (est.codigo || est.id || '').toUpperCase();
        this.estacionesMap.set(cod, est);
      });

      (this.troncalesData || []).forEach(t => {
        this.troncalesMap.set(t.id, t);
      });
    }

    _createDOM() {
      this.container.innerHTML = '';
      this.container.style.position = 'relative';
      this.container.style.overflow = 'hidden';
      this.container.style.userSelect = 'none';
      this.container.tabIndex = 0;
      this.container.setAttribute('role', 'region');
      this.container.setAttribute('aria-label', 'Diagrama esquemático interactivo de la red de TransMilenio');

      // Crear SVG
      this.svg = document.createElementNS(SVG_NS, 'svg');
      const vb = this.layout.viewBox || { width: 1750, height: 1050 };
      this.svg.setAttribute('viewBox', `0 0 ${vb.width} ${vb.height}`);
      this.svg.setAttribute('width', '100%');
      this.svg.setAttribute('height', '100%');
      this.svg.classList.add('tm-schematic-svg');
      this.svg.style.display = 'block';
      this.svg.style.cursor = 'grab';
      this.svg.style.touchAction = 'none';

      // Definiciones (filtros, halos)
      const defs = document.createElementNS(SVG_NS, 'defs');
      
      // Filtro Glow suave
      const filter = document.createElementNS(SVG_NS, 'filter');
      filter.setAttribute('id', 'tm-glow');
      filter.setAttribute('x', '-30%');
      filter.setAttribute('y', '-30%');
      filter.setAttribute('width', '160%');
      filter.setAttribute('height', '160%');
      const feDrop = document.createElementNS(SVG_NS, 'feDropShadow');
      feDrop.setAttribute('dx', '0');
      feDrop.setAttribute('dy', '0');
      feDrop.setAttribute('stdDeviation', '4');
      feDrop.setAttribute('flood-color', 'var(--rojo, #E8001D)');
      feDrop.setAttribute('flood-opacity', '0.7');
      filter.appendChild(feDrop);
      defs.appendChild(filter);

      this.svg.appendChild(defs);

      // Grupo Viewport para Pan & Zoom
      this.viewportGroup = document.createElementNS(SVG_NS, 'g');
      this.viewportGroup.setAttribute('class', 'tm-viewport');

      // Capas en orden de apilamiento (Z-index en SVG)
      this.connectionsGroup = document.createElementNS(SVG_NS, 'g');
      this.connectionsGroup.setAttribute('class', 'tm-layer-connections');

      this.corridorsGroup = document.createElementNS(SVG_NS, 'g');
      this.corridorsGroup.setAttribute('class', 'tm-layer-corridors');

      this.stationsGroup = document.createElementNS(SVG_NS, 'g');
      this.stationsGroup.setAttribute('class', 'tm-layer-stations');

      this.viewportGroup.appendChild(this.connectionsGroup);
      this.viewportGroup.appendChild(this.corridorsGroup);
      this.viewportGroup.appendChild(this.stationsGroup);
      this.svg.appendChild(this.viewportGroup);

      this.container.appendChild(this.svg);

      // Tooltip HTML flotante
      this.tooltip = document.createElement('div');
      this.tooltip.className = 'tm-schematic-tooltip';
      this.tooltip.setAttribute('role', 'tooltip');
      this.tooltip.setAttribute('aria-hidden', 'true');
      this.tooltip.id = 'tm-station-tooltip';
      Object.assign(this.tooltip.style, {
        position: 'fixed',
        pointerEvents: 'none',
        zIndex: '2147483000',
        opacity: '1',
        filter: 'none',
        backdropFilter: 'none',
        mixBlendMode: 'normal',
        transform: 'none',
        transition: 'none',
        animation: 'none',
        backgroundColor: '#111927',
        color: '#f1f5f9'
      });
      document.body.appendChild(this.tooltip);

      // Botones flotantes de Pan & Zoom
      this._createZoomControls();
    }

    _createZoomControls() {
      const controls = document.createElement('div');
      controls.className = 'tm-zoom-controls';
      controls.setAttribute('role', 'toolbar');
      controls.setAttribute('aria-label', 'Controles de vista del mapa esquemático');

      const btnZoomIn = this._createBtn('+', 'Ampliar zoom (Acercar)', () => this.zoom(1.25));
      const btnZoomOut = this._createBtn('−', 'Reducir zoom (Alejar)', () => this.zoom(0.8));
      const btnReset = this._createBtn('🎯', 'Centrar y restablecer vista', () => this.resetView());

      controls.appendChild(btnZoomIn);
      controls.appendChild(btnZoomOut);
      controls.appendChild(btnReset);

      this.container.appendChild(controls);
    }

    _createBtn(label, title, onClick) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tm-zoom-btn';
      btn.textContent = label;
      btn.title = title;
      btn.setAttribute('aria-label', title);
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      });
      return btn;
    }

    _bindEvents() {
      const svgPoint = (clientX, clientY) => {
        const point = this.svg.createSVGPoint();
        point.x = clientX;
        point.y = clientY;
        return point.matrixTransform(this.svg.getScreenCTM().inverse());
      };
      const stationNode = (target) => {
        const node = target && target.closest ? target.closest('.tm-station-node') : null;
        return node && this.stationsGroup.contains(node) ? node : null;
      };
      this.stationsGroup.addEventListener('pointerover', (event) => {
        if (event.pointerType === 'touch') return;
        this.inputMode = 'mouse';
        const node = stationNode(event.target);
        if (node) this._showTooltip(node.dataset.code, node);
      });
      this.stationsGroup.addEventListener('pointerout', (event) => {
        const node = stationNode(event.target);
        if (!node || node !== this.hoveredNode) return;
        if (stationNode(event.relatedTarget)) return;
        this._hideTooltip();
      });
      this.stationsGroup.addEventListener('pointerdown', (event) => {
        if (event.pointerType === 'touch') {
          this.inputMode = 'touch';
          this._hideTooltip();
        }
      });
      this.stationsGroup.addEventListener('focusin', (event) => {
        if (this.inputMode === 'touch') return;
        const node = stationNode(event.target);
        if (node) this._showTooltip(node.dataset.code, node);
      });
      this.stationsGroup.addEventListener('focusout', (event) => {
        if (!stationNode(event.relatedTarget)) this._hideTooltip();
      });
      this.stationsGroup.addEventListener('click', (event) => {
        const node = stationNode(event.target);
        if (!node) return;
        event.stopPropagation();
        this.selectStation(node.dataset.code);
      });
      this.stationsGroup.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const node = stationNode(event.target);
        if (!node) return;
        event.preventDefault();
        this.selectStation(node.dataset.code);
      });
      this._onWindowKeyDown = () => { this.inputMode = 'keyboard'; };
      window.addEventListener('keydown', this._onWindowKeyDown);
      // Pan con mouse
      this.svg.addEventListener('mousedown', (e) => {
        if (e.target.closest('.tm-station-node') || e.target.closest('.tm-zoom-btn')) return;
        const point = svgPoint(e.clientX, e.clientY);
        this._mousePanStart = {
          clientX: e.clientX, clientY: e.clientY,
          pointX: point.x, pointY: point.y,
          panX: this.panX, panY: this.panY
        };
      });

      this._onWindowMouseMove = (e) => {
        if (!this._mousePanStart) return;
        const start = this._mousePanStart;
        if (!this.isPanning &&
            Math.hypot(e.clientX - start.clientX, e.clientY - start.clientY) < 5) return;
        if (!this.isPanning) {
          this.isPanning = true;
          this._hideTooltip();
          this.svg.style.cursor = 'grabbing';
        }
        const point = svgPoint(e.clientX, e.clientY);
        this.panX = start.panX + point.x - start.pointX;
        this.panY = start.panY + point.y - start.pointY;
        this._updateTransform();
      };
      window.addEventListener('mousemove', this._onWindowMouseMove);

      this._onWindowMouseUp = () => {
        this._mousePanStart = null;
        this.isPanning = false;
        this.svg.style.cursor = 'grab';
      };
      window.addEventListener('mouseup', this._onWindowMouseUp);

      // Zoom con rueda de ratón (centrado en el cursor)
      this.svg.addEventListener('wheel', (e) => {
        e.preventDefault();
        const point = svgPoint(e.clientX, e.clientY);
        const factor = e.deltaY < 0 ? 1.15 : 0.85;
        this.zoomAtPoint(factor, point.x, point.y);
      }, { passive: false });

      // Soporte Touch para móviles y tablets
      let previousPinchDist = 0;
      let touchStart = null;

      this.svg.addEventListener('touchstart', (e) => {
        this.inputMode = 'touch';
        this._hideTooltip();
        if (e.touches.length === 1) {
          const point = svgPoint(e.touches[0].clientX, e.touches[0].clientY);
          this.isPanning = false;
          touchStart = {
            clientX: e.touches[0].clientX, clientY: e.touches[0].clientY,
            pointX: point.x, pointY: point.y,
            panX: this.panX, panY: this.panY
          };
        } else if (e.touches.length === 2) {
          this.isPanning = false;
          touchStart = null;
          previousPinchDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
        }
      }, { passive: true });

      this.svg.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1 && touchStart) {
          if (!this.isPanning &&
              Math.hypot(e.touches[0].clientX - touchStart.clientX,
                e.touches[0].clientY - touchStart.clientY) < 8) return;
          e.preventDefault();
          this.isPanning = true;
          const point = svgPoint(e.touches[0].clientX, e.touches[0].clientY);
          this.panX = touchStart.panX + point.x - touchStart.pointX;
          this.panY = touchStart.panY + point.y - touchStart.pointY;
          this._updateTransform();
        } else if (e.touches.length === 2 && previousPinchDist > 0) {
          e.preventDefault();
          const currentDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
          const midpoint = svgPoint(
            (e.touches[0].clientX + e.touches[1].clientX) / 2,
            (e.touches[0].clientY + e.touches[1].clientY) / 2
          );
          this.zoomAtPoint(currentDist / previousPinchDist, midpoint.x, midpoint.y);
          previousPinchDist = currentDist;
        }
      }, { passive: false });

      this.svg.addEventListener('touchend', () => {
        this.isPanning = false;
        touchStart = null;
        previousPinchDist = 0;
      });
      this.svg.addEventListener('touchcancel', () => {
        this.isPanning = false;
        touchStart = null;
        previousPinchDist = 0;
      });

      // Accesibilidad de teclado en el contenedor
      this.container.addEventListener('keydown', (e) => {
        const step = 40;
        if (e.key === 'ArrowRight') { this.panX -= step; this._updateTransform(); e.preventDefault(); }
        else if (e.key === 'ArrowLeft') { this.panX += step; this._updateTransform(); e.preventDefault(); }
        else if (e.key === 'ArrowDown') { this.panY -= step; this._updateTransform(); e.preventDefault(); }
        else if (e.key === 'ArrowUp') { this.panY += step; this._updateTransform(); e.preventDefault(); }
        else if (e.key === '+' || e.key === '=') { this.zoom(1.2); e.preventDefault(); }
        else if (e.key === '-' || e.key === '_') { this.zoom(0.8); e.preventDefault(); }
        else if (e.key === '0') { this.resetView(); e.preventDefault(); }
      });
    }

    _updateTransform() {
      if (!this.viewportGroup) return;
      this.viewportGroup.setAttribute(
        'transform',
        `matrix(${this.scale} 0 0 ${this.scale} ${this.panX} ${this.panY})`
      );
      if (this.hoveredNode) this._positionTooltip(this.hoveredNode);
    }

    zoom(factor) {
      const vb = this.layout.viewBox || { width: 1750, height: 1050 };
      this.zoomAtPoint(factor, vb.width / 2, vb.height / 2);
    }

    zoomAtPoint(factor, px, py) {
      const oldScale = this.scale;
      const newScale = Math.min(Math.max(this.scale * factor, 0.45), 4.0);
      if (newScale === oldScale) return;

      // Mantener punto de mouse estacionario
      this.panX = px - (px - this.panX) * (newScale / oldScale);
      this.panY = py - (py - this.panY) * (newScale / oldScale);
      this.scale = newScale;
      this._updateTransform();
    }

    resetView() {
      const vb = this.layout.viewBox || { width: 1750, height: 1050 };
      this.scale = 0.94;
      this.panX = vb.width * (1 - this.scale) / 2;
      this.panY = vb.height * (1 - this.scale) / 2;
      this._updateTransform();
    }

    centerOnStation(codigo) {
      const stLayout = (this.layout.stations || {})[codigo];
      if (!stLayout) return;

      const vb = this.layout.viewBox || { width: 1750, height: 1050 };
      this.scale = Math.max(this.scale, 1.4);
      this.panX = vb.width / 2 - stLayout.x * this.scale;
      this.panY = vb.height / 2 - stLayout.y * this.scale;
      this._updateTransform();
    }

    hasStationPosition(codigo) {
      const code = String(codigo || '').toUpperCase();
      return Boolean((this.layout.stations || {})[code]);
    }

    updateData(estaciones, troncales) {
      if (estaciones) this.estacionesData = estaciones;
      if (troncales) this.troncalesData = troncales;
      this._indexData();
      this.render();
    }

    setFilters({ troncal, estado, busqueda }) {
      if (troncal !== undefined) this.troncalFiltro = troncal;
      if (estado !== undefined) this.filtroEstado = estado;
      if (busqueda !== undefined) this.busqueda = (busqueda || '').trim().toLowerCase();
      this.render();
    }

    render() {
      this._hideTooltip();
      this._renderCorridors();
      this._renderConnections();
      this._renderStations();
    }

    _renderCorridors() {
      this.corridorsGroup.innerHTML = '';

      (this.layout.corridors || []).forEach(corr => {
        const pathEl = document.createElementNS(SVG_NS, 'path');
        pathEl.setAttribute('d', corr.path);
        pathEl.setAttribute('class', `tm-corridor tm-corridor-${corr.id}`);
        pathEl.setAttribute('stroke', corr.color || '#888');
        pathEl.setAttribute('stroke-linecap', 'round');
        pathEl.setAttribute('stroke-linejoin', 'round');
        pathEl.setAttribute('fill', 'none');

        // Atenuación o resalte según filtro
        const isActiveTroncal = !this.troncalFiltro || corr.troncalId === this.troncalFiltro;
        if (!isActiveTroncal) {
          pathEl.classList.add('tm-corridor--dimmed');
        } else if (this.troncalFiltro) {
          pathEl.classList.add('tm-corridor--highlighted');
        }

        this.corridorsGroup.appendChild(pathEl);
      });
    }

    _renderConnections() {
      this.connectionsGroup.innerHTML = '';

      (this.layout.connections || []).forEach(conn => {
        const pathEl = document.createElementNS(SVG_NS, 'path');
        pathEl.setAttribute('d', conn.path);
        pathEl.setAttribute('class', 'tm-connection');
        pathEl.setAttribute('fill', 'none');
        pathEl.setAttribute('stroke-dasharray', '5 4');
        this.connectionsGroup.appendChild(pathEl);
      });
    }

    _renderStations() {
      this.stationsGroup.innerHTML = '';

      const layoutStations = this.layout.stations || {};
      const stationEntries = Object.entries(layoutStations);

      stationEntries.forEach(([codigo, stPos]) => {
        const apiData = this.estacionesMap.get(codigo);

        // Si no existe en layout, ignorar con advertencia interna
        if (!stPos) return;

        // Evaluación de filtros
        const matchesTroncal = !this.troncalFiltro || (apiData && apiData.troncal_id === this.troncalFiltro) || stPos.troncalId === this.troncalFiltro;
        
        let matchesEstado = true;
        if (this.filtroEstado === 'con_camaras') {
          matchesEstado = apiData && apiData.camaras && apiData.camaras.total > 0;
        } else if (this.filtroEstado === 'con_evasiones') {
          matchesEstado = apiData && apiData.eventos_hoy && apiData.eventos_hoy.total_hoy > 0;
        }

        let matchesBusqueda = true;
        if (this.busqueda) {
          const consulta = normalizarBusqueda(this.busqueda);
          const nombres = apiData ? [apiData.nombre, ...(apiData.aliases || [])] : [];
          const cod = normalizarBusqueda(codigo);
          matchesBusqueda = nombres.some(nombre => normalizarBusqueda(nombre).includes(consulta)) || cod.includes(consulta);
        }

        const isDimmed = !matchesTroncal || !matchesEstado || (this.busqueda && !matchesBusqueda);

        // Grupo de la estación (interactivo y accesible)
        const g = document.createElementNS(SVG_NS, 'g');
        g.setAttribute('class', 'tm-station-node');
        g.setAttribute('transform', `translate(${stPos.x}, ${stPos.y})`);
        g.setAttribute('role', 'button');
        g.setAttribute('tabindex', '0');
        g.dataset.code = codigo;

        const nombreEst = apiData ? apiData.nombre : codigo;
        g.setAttribute('aria-label', `Estación ${nombreEst} (${codigo})`);

        if (isDimmed) g.classList.add('tm-station--dimmed');
        if (this.estacionSeleccionada === codigo) g.classList.add('tm-station--selected');

        // Estado semántico de riesgo y cámaras
        const riesgo = apiData ? (apiData.riesgo || 'normal') : 'normal';
        const tieneCamaras = apiData && apiData.camaras && apiData.camaras.total > 0;
        // Asignar clase de estado
        if (riesgo === 'critico') {
          g.classList.add('tm-status-critical');
        } else if (riesgo === 'alerta') {
          g.classList.add('tm-status-warning');
        } else if (tieneCamaras) {
          g.classList.add('tm-status-monitored');
        } else {
          g.classList.add('tm-status-unmonitored');
        }

        // Tipo visual de estación
        const isPortal = stPos.tipo === 'portal' || (apiData && apiData.tipo === 'portal');
        const isInterchange = stPos.interchange || stPos.tipo === 'intermedio';
        const nearest = stationEntries.reduce((minimum, [otherCode, other]) => {
          if (otherCode === codigo) return minimum;
          return Math.min(minimum, Math.hypot(stPos.x - other.x, stPos.y - other.y));
        }, Infinity);
        const hit = document.createElementNS(SVG_NS, 'circle');
        hit.setAttribute('r', String(Math.min(11, Math.max(4.5, nearest / 2 - 0.75))));
        hit.setAttribute('class', 'tm-station-hit');
        hit.setAttribute('fill', 'transparent');
        hit.setAttribute('pointer-events', 'all');
        g.appendChild(hit);

        if (isPortal) {
          // Portales: Nodo mayor con doble contorno cuadrado o hexágono
          const rect = document.createElementNS(SVG_NS, 'rect');
          rect.setAttribute('x', '-9');
          rect.setAttribute('y', '-9');
          rect.setAttribute('width', '18');
          rect.setAttribute('height', '18');
          rect.setAttribute('rx', '4');
          rect.setAttribute('class', 'tm-station-shape tm-portal-shape');
          g.appendChild(rect);

          const innerCircle = document.createElementNS(SVG_NS, 'circle');
          innerCircle.setAttribute('r', '4.5');
          innerCircle.setAttribute('class', 'tm-portal-center');
          g.appendChild(innerCircle);
        } else if (isInterchange) {
          // Transbordos / Intermedios: Círculo con doble anillo concéntrico
          const outerCircle = document.createElementNS(SVG_NS, 'circle');
          outerCircle.setAttribute('r', '7.5');
          outerCircle.setAttribute('class', 'tm-station-shape tm-interchange-outer');
          g.appendChild(outerCircle);

          const innerCircle = document.createElementNS(SVG_NS, 'circle');
          innerCircle.setAttribute('r', '4');
          innerCircle.setAttribute('class', 'tm-interchange-inner');
          g.appendChild(innerCircle);
        } else {
          // Estación regular: Círculo de paso limpio
          const circle = document.createElementNS(SVG_NS, 'circle');
          circle.setAttribute('r', '5.5');
          circle.setAttribute('class', 'tm-station-shape tm-regular-node');
          g.appendChild(circle);
        }

        this.stationsGroup.appendChild(g);
      });
    }

    selectStation(codigo) {
      this._hideTooltip();
      this.estacionSeleccionada = codigo;
      this.render();
      if (this.onSelectStation) {
        this.onSelectStation(codigo);
      }
    }

    _showTooltip(codigo, node) {
      if (!this.tooltip || !node) return;
      if (this.hoveredCode === codigo && this.hoveredNode === node) {
        this._positionTooltip(node);
        return;
      }
      this._hideTooltip();
      const data = this.estacionesMap.get(codigo);
      const position = (this.layout.stations || {})[codigo];
      const name = data && data.nombre ? data.nombre : codigo;
      const trunkId = data && data.troncal_id ? data.troncal_id : position && position.troncalId;
      const trunkName = data && data.troncal
        ? data.troncal : this.troncalesMap.get(trunkId)?.nombre;
      const trunkText = trunkName
        ? `${trunkId ? trunkId + ' - ' : ''}${trunkName}` : trunkId || '';
      const state = data && data.estado_operativo
        ? ESTADOS_OPERATIVOS_LABELS[data.estado_operativo] || 'No disponible' : null;
      const cameras = data && data.camaras;
      const cameraTotal = cameras && Number.isFinite(cameras.total) ? cameras.total : null;
      const cameraActive = cameras && Number.isFinite(cameras.activas) ? cameras.activas : null;
      const events = data && data.eventos_hoy;
      const eventsToday = events && Number.isFinite(events.total_hoy) ? events.total_hoy : null;
      const risk = data && data.riesgo;
      const cameraText = cameraTotal === null ? '' : cameraActive === null
        ? `${cameraTotal} asociadas - activas sin dato`
        : `${cameraActive} / ${cameraTotal} activas`;
      const riskText = risk === 'critico' ? 'Riesgo crítico'
        : risk === 'alerta' ? 'Riesgo de alerta' : '';
      this.tooltip.innerHTML = `
        <div class="tm-tip-header">
          <strong class="tm-tip-title">${this._escapeHTML(name)}</strong>
          <span class="tm-tip-code">${this._escapeHTML(codigo)}</span>
        </div>
        ${trunkText ? `<div class="tm-tip-meta">${this._escapeHTML(trunkText)}</div>` : ''}
        ${state ? `<div class="tm-tip-row"><span>Estado</span><strong>${this._escapeHTML(state)}</strong></div>` : ''}
        ${cameraTotal !== null ? `<div class="tm-tip-row"><span>Cámaras</span><strong>${this._escapeHTML(cameraText)}</strong></div>` : ''}
        ${eventsToday !== null ? `<div class="tm-tip-row"><span>Evasiones hoy</span><strong>${eventsToday}</strong></div>` : ''}
        ${riskText ? `<div class="tm-tip-footer">${this._escapeHTML(riskText)}</div>` : ''}
      `;
      this.hoveredCode = codigo;
      this.hoveredNode = node;
      node.classList.add('tm-station--hovered');
      node.setAttribute('aria-describedby', this.tooltip.id);
      this._positionTooltip(node);
      this.tooltip.classList.add('is-visible');
      this.tooltip.setAttribute('aria-hidden', 'false');
    }

    _positionTooltip(node) {
      if (!this.tooltip || !node) return;
      const box = node.getBoundingClientRect();
      const width = this.tooltip.offsetWidth;
      const height = this.tooltip.offsetHeight;
      const margin = 8;
      const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
      const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
      let left = box.right + 12;
      if (left + width + margin > viewportWidth) left = box.left - width - 12;
      let top = box.top + box.height / 2 - height / 2;
      left = Math.max(margin, Math.min(left, viewportWidth - width - margin));
      top = Math.max(margin, Math.min(top, viewportHeight - height - margin));
      this.tooltip.style.left = `${left}px`;
      this.tooltip.style.top = `${top}px`;
    }

    _hideTooltip() {
      if (!this.tooltip) return;
      if (this.hoveredNode) {
        this.hoveredNode.classList.remove('tm-station--hovered');
        this.hoveredNode.removeAttribute('aria-describedby');
      }
      this.hoveredCode = null;
      this.hoveredNode = null;
      this.tooltip.classList.remove('is-visible');
      this.tooltip.setAttribute('aria-hidden', 'true');
    }

    _escapeHTML(str) {
      return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    destroy() {
      this._hideTooltip();
      if (this.tooltip) this.tooltip.remove();
      window.removeEventListener('mousemove', this._onWindowMouseMove);
      window.removeEventListener('mouseup', this._onWindowMouseUp);
      window.removeEventListener('keydown', this._onWindowKeyDown);
      this.container.innerHTML = '';
      this.estacionesMap.clear();
      this.troncalesMap.clear();
    }
  }

  return TransmilenioSchematicMap;
}));
