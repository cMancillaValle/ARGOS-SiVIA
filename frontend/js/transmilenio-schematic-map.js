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
      this.startX = 0;
      this.startY = 0;

      // Elementos SVG
      this.svg = null;
      this.viewportGroup = null;
      this.corridorsGroup = null;
      this.connectionsGroup = null;
      this.stationsGroup = null;
      this.labelsGroup = null;
      this.tooltip = null;

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

      this.labelsGroup = document.createElementNS(SVG_NS, 'g');
      this.labelsGroup.setAttribute('class', 'tm-layer-labels');

      this.viewportGroup.appendChild(this.connectionsGroup);
      this.viewportGroup.appendChild(this.corridorsGroup);
      this.viewportGroup.appendChild(this.stationsGroup);
      this.viewportGroup.appendChild(this.labelsGroup);
      this.svg.appendChild(this.viewportGroup);

      this.container.appendChild(this.svg);

      // Tooltip HTML flotante
      this.tooltip = document.createElement('div');
      this.tooltip.className = 'tm-schematic-tooltip';
      this.tooltip.setAttribute('role', 'tooltip');
      this.tooltip.setAttribute('aria-hidden', 'true');
      this.container.appendChild(this.tooltip);

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
      // Pan con mouse
      this.svg.addEventListener('mousedown', (e) => {
        if (e.target.closest('.tm-station-node') || e.target.closest('.tm-zoom-btn')) return;
        this.isPanning = true;
        this.startX = e.clientX - this.panX;
        this.startY = e.clientY - this.panY;
        this.svg.style.cursor = 'grabbing';
      });

      window.addEventListener('mousemove', (e) => {
        if (!this.isPanning) return;
        this.panX = e.clientX - this.startX;
        this.panY = e.clientY - this.startY;
        this._updateTransform();
      });

      window.addEventListener('mouseup', () => {
        if (this.isPanning) {
          this.isPanning = false;
          this.svg.style.cursor = 'grab';
        }
      });

      // Zoom con rueda de ratón (centrado en el cursor)
      this.svg.addEventListener('wheel', (e) => {
        e.preventDefault();
        const rect = this.container.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        const factor = e.deltaY < 0 ? 1.15 : 0.85;
        this.zoomAtPoint(factor, mouseX, mouseY);
      }, { passive: false });

      // Soporte Touch para móviles y tablets
      let initialPinchDist = 0;
      let initialScale = 1;

      this.svg.addEventListener('touchstart', (e) => {
        if (e.touches.length === 1) {
          this.isPanning = true;
          this.startX = e.touches[0].clientX - this.panX;
          this.startY = e.touches[0].clientY - this.panY;
        } else if (e.touches.length === 2) {
          this.isPanning = false;
          initialPinchDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
          initialScale = this.scale;
        }
      }, { passive: true });

      this.svg.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1 && this.isPanning) {
          this.panX = e.touches[0].clientX - this.startX;
          this.panY = e.touches[0].clientY - this.startY;
          this._updateTransform();
        } else if (e.touches.length === 2 && initialPinchDist > 0) {
          const currentDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
          const factor = currentDist / initialPinchDist;
          this.scale = Math.min(Math.max(initialScale * factor, 0.4), 4.5);
          this._updateTransform();
        }
      }, { passive: true });

      this.svg.addEventListener('touchend', () => {
        this.isPanning = false;
        initialPinchDist = 0;
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
    }

    zoom(factor) {
      const rect = this.container.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      this.zoomAtPoint(factor, cx, cy);
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
      const rect = this.container.getBoundingClientRect();
      const vb = this.layout.viewBox || { width: 1750, height: 1050 };
      
      const scaleX = rect.width / vb.width;
      const scaleY = rect.height / vb.height;
      this.scale = Math.min(scaleX, scaleY) * 0.94 || 0.75;

      this.panX = (rect.width - vb.width * this.scale) / 2;
      this.panY = (rect.height - vb.height * this.scale) / 2;
      this._updateTransform();
    }

    centerOnStation(codigo) {
      const stLayout = (this.layout.stations || {})[codigo];
      if (!stLayout) return;

      const rect = this.container.getBoundingClientRect();
      this.scale = Math.max(this.scale, 1.4);
      this.panX = (rect.width / 2) - (stLayout.x * this.scale);
      this.panY = (rect.height / 2) - (stLayout.y * this.scale);
      this._updateTransform();
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
      this.labelsGroup.innerHTML = '';

      const layoutStations = this.layout.stations || {};

      Object.keys(layoutStations).forEach(codigo => {
        const stPos = layoutStations[codigo];
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
          const nom = apiData ? apiData.nombre.toLowerCase() : '';
          const cod = codigo.toLowerCase();
          matchesBusqueda = nom.includes(this.busqueda) || cod.includes(this.busqueda);
        }

        const isVisible = matchesTroncal && matchesEstado && matchesBusqueda;
        const isDimmed = !matchesTroncal || !matchesEstado || (this.busqueda && !matchesBusqueda);

        // Grupo de la estación (interactivo y accesible)
        const g = document.createElementNS(SVG_NS, 'g');
        g.setAttribute('class', 'tm-station-node');
        g.setAttribute('transform', `translate(${stPos.x}, ${stPos.y})`);
        g.setAttribute('role', 'button');
        g.setAttribute('tabindex', '0');

        const nombreEst = apiData ? apiData.nombre : codigo;
        g.setAttribute('aria-label', `Estación ${nombreEst} (${codigo})`);

        if (isDimmed) g.classList.add('tm-station--dimmed');
        if (this.estacionSeleccionada === codigo) g.classList.add('tm-station--selected');

        // Estado semántico de riesgo y cámaras
        const riesgo = apiData ? (apiData.riesgo || 'normal') : 'normal';
        const tieneCamaras = apiData && apiData.camaras && apiData.camaras.total > 0;
        const totalEv = apiData && apiData.eventos_hoy ? apiData.eventos_hoy.total_hoy : 0;

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

        // Eventos interactivos en la estación
        g.addEventListener('click', (e) => {
          e.stopPropagation();
          this.selectStation(codigo);
        });

        g.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.selectStation(codigo);
          }
        });

        g.addEventListener('mouseenter', (e) => this._showTooltip(e, codigo));
        g.addEventListener('mousemove', (e) => this._moveTooltip(e));
        g.addEventListener('mouseleave', () => this._hideTooltip());
        g.addEventListener('focus', (e) => this._showTooltip(e, codigo));
        g.addEventListener('blur', () => this._hideTooltip());

        this.stationsGroup.appendChild(g);

        // Renderizar Etiqueta de texto (limpia y sin overlap)
        if (isVisible) {
          const textEl = document.createElementNS(SVG_NS, 'text');
          textEl.setAttribute('x', String(stPos.x + (stPos.labelOffsetX || 8)));
          textEl.setAttribute('y', String(stPos.y + (stPos.labelOffsetY || 3)));
          textEl.setAttribute('class', 'tm-station-label');
          
          if (stPos.labelPosition === 'left') {
            textEl.setAttribute('text-anchor', 'end');
          } else if (stPos.labelPosition === 'top' || stPos.labelPosition === 'bottom') {
            textEl.setAttribute('text-anchor', 'middle');
          } else {
            textEl.setAttribute('text-anchor', 'start');
          }

          if (isPortal) textEl.classList.add('tm-label-portal');
          if (this.estacionSeleccionada === codigo) textEl.classList.add('tm-label--selected');

          // Uso seguro de textContent
          textEl.textContent = nombreEst;
          this.labelsGroup.appendChild(textEl);
        }
      });
    }

    selectStation(codigo) {
      this.estacionSeleccionada = codigo;
      this.render();
      if (this.onSelectStation) {
        this.onSelectStation(codigo);
      }
    }

    _showTooltip(e, codigo) {
      if (!this.tooltip) return;
      const apiData = this.estacionesMap.get(codigo);
      const stPos = (this.layout.stations || {})[codigo];

      const nombre = apiData ? apiData.nombre : codigo;
      const troncal = apiData ? apiData.troncal : (stPos ? `Troncal ${stPos.troncalId}` : '');
      const totalCam = apiData && apiData.camaras ? apiData.camaras.total : 0;
      const camAct = apiData && apiData.camaras ? apiData.camaras.activas : 0;
      const evHoy = apiData && apiData.eventos_hoy ? apiData.eventos_hoy.total_hoy : 0;
      const riesgo = apiData ? (apiData.riesgo || 'normal') : 'normal';

      let riesgoBadge = '<span class="tm-tip-badge tm-badge-normal">Operación Normal</span>';
      if (riesgo === 'critico') {
        riesgoBadge = '<span class="tm-tip-badge tm-badge-critical">Alerta Crítica</span>';
      } else if (riesgo === 'alerta') {
        riesgoBadge = '<span class="tm-tip-badge tm-badge-warning">Alerta Moderada</span>';
      }

      this.tooltip.innerHTML = `
        <div class="tm-tip-header">
          <strong class="tm-tip-title">${this._escapeHTML(nombre)}</strong>
          <span class="tm-tip-code">${this._escapeHTML(codigo)}</span>
        </div>
        <div class="tm-tip-meta">${this._escapeHTML(troncal)}</div>
        <div class="tm-tip-body">
          <div class="tm-tip-row">
            <span>📹 Cámaras:</span>
            <strong>${camAct} / ${totalCam} activas</strong>
          </div>
          <div class="tm-tip-row">
            <span>🚨 Evasiones hoy:</span>
            <strong class="${evHoy > 0 ? 'tm-text-alert' : ''}">${evHoy}</strong>
          </div>
          <div class="tm-tip-footer">
            ${riesgoBadge}
          </div>
        </div>
      `;

      this.tooltip.classList.add('is-visible');
      this.tooltip.setAttribute('aria-hidden', 'false');
      this._moveTooltip(e);
    }

    _moveTooltip(e) {
      if (!this.tooltip || !this.tooltip.classList.contains('is-visible')) return;
      const rect = this.container.getBoundingClientRect();
      const clientX = e.clientX || (e.target && e.target.getBoundingClientRect ? e.target.getBoundingClientRect().left + 10 : 0);
      const clientY = e.clientY || (e.target && e.target.getBoundingClientRect ? e.target.getBoundingClientRect().top - 10 : 0);

      const x = clientX - rect.left + 12;
      const y = clientY - rect.top - 10;

      this.tooltip.style.left = `${Math.min(x, rect.width - 240)}px`;
      this.tooltip.style.top = `${Math.max(10, Math.min(y, rect.height - 130))}px`;
    }

    _hideTooltip() {
      if (!this.tooltip) return;
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
      this.container.innerHTML = '';
      this.estacionesMap.clear();
      this.troncalesMap.clear();
    }
  }

  return TransmilenioSchematicMap;
}));
