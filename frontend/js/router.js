/**
 * frontend/js/router.js  -  ARGOS SiViA SPA Router v1.7.5
 * ─────────────────────────────────────────────────────────
 * v1.7.5:
 *  - updateSidebarActive usa las clases del sistema nuevo (.is-active, .is-expanded, .nav-sublink.is-active)
 *  - Delegación: [data-module] y [data-in-construction]
 *  - Modal construcción con CSS vars (dark/light)
 *  - Usuarios_rbac alias por data-module="usuarios_rbac"
 */

const AppRouter = (() => {
  // ─── Mapa de módulos ─────────────────────────────────────────────────────────
  const MODULES = {
    home:              { file: 'dashboard_home.html',  roles: null },
    camaras:           { file: 'camaras.html',         roles: ['admin','supervisor','operador','analista','tecnico','auditor'] },
    eventos:           { file: 'eventos.html',         roles: ['admin','supervisor','operador','analista','tecnico','auditor'] },
    estadisticas:      { file: 'estadisticas.html',    roles: ['admin','supervisor','operador','analista'] },
    configuracion:     { file: 'configuracion.html',   roles: ['admin','tecnico'] },
    auditoria:         { file: 'auditoria.html',       roles: ['admin','auditor','supervisor'] },
    usuarios_rbac:     { file: 'usuarios_rbac.html',   roles: ['admin'] },
    infra_camaras:     { file: 'infra_camaras.html',   roles: ['admin','supervisor','tecnico'] },
    infra_red:         { file: 'infra_red.html',       roles: ['admin','supervisor','tecnico'] },
    infra_servidores:  { file: 'infra_servidores.html',roles: ['admin','supervisor','tecnico'] },
    notificaciones:    { file: 'notificaciones.html',  roles: ['admin','supervisor','operador','analista','tecnico','auditor'] },
    parametros:        { file: 'parametros.html',      roles: ['admin','tecnico'] },
    reportes:          { file: 'reportes.html',        roles: ['admin','supervisor','analista'] },
    torniquetes:       { file: 'notificaciones.html',  roles: ['admin','supervisor','operador'] }, // placeholder hasta crear vista
  };

  let _firstLoad = true;

  // ─── URL helpers ─────────────────────────────────────────────────────────────
  function getBasePath() { return window.location.origin + '/'; }
  function getQueryModule() {
    return new URLSearchParams(window.location.search).get('module') || 'home';
  }
  function setQueryModule(mod) {
    const url = new URL(window.location);
    url.searchParams.set('module', mod);
    window.history.pushState({ module: mod }, '', url);
  }

  // ─── Carga de componentes layout ─────────────────────────────────────────────
  async function loadComponent(containerId, filename) {
    const url = getBasePath() + 'components/' + filename;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status} → ${url}`);
      const container = document.getElementById(containerId);
      container.innerHTML = await res.text();
      // Ejecutar scripts del componente
      container.querySelectorAll('script').forEach(old => {
        const s = document.createElement('script');
        s.textContent = old.textContent;
        document.head.appendChild(s).remove();
      });
    } catch (e) {
      console.error('[Router] loadComponent falló:', e.message);
    }
  }

  // ─── Carga de vista (módulo) ──────────────────────────────────────────────────
  async function loadView(filename) {
    const url  = getBasePath() + 'views/' + filename;
    const main = document.getElementById('main-content');

    // ── IMPORTANTE: disparar navaway ANTES de reemplazar el DOM ───────────────
    // Permite que los módulos (ej: dashboard_home) limpien sus setIntervals
    // y eviten "Cannot set properties of null" en callbacks pendientes.
    document.dispatchEvent(new CustomEvent('argos:navaway'));

    // Mini-loader inline  (NO fullscreen - ese solo es en la primera carga)
    main.innerHTML = `
      <div class="flex items-center justify-center h-64">
        <div class="flex flex-col items-center gap-3">
          <div class="w-8 h-8 border-2 rounded-full animate-spin"
               style="border-color:var(--rojo);border-top-color:transparent"></div>
          <div class="font-mono text-xs tracking-widest uppercase"
               style="color:var(--dim)">Cargando módulo...</div>
        </div>
      </div>`;

    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status} → ${url}`);
      main.innerHTML = await res.text();

      if (window.RBAC && typeof RBAC.aplicarUI === 'function') RBAC.aplicarUI();

      // Ejecutar scripts del HTML cargado (innerHTML no los ejecuta)
      main.querySelectorAll('script').forEach(old => {
        const s = document.createElement('script');
        s.textContent = old.textContent;
        document.head.appendChild(s).remove();
      });

    } catch (e) {
      console.error('[Router] loadView falló:', e.message);
      main.innerHTML = `
        <div class="flex flex-col items-center justify-center h-64 gap-4">
          <div class="text-5xl">⚠️</div>
          <div class="font-rajdhani text-xl font-bold" style="color:var(--rojo)">Error cargando módulo</div>
          <div class="font-mono text-xs" style="color:var(--dim)">${e.message}</div>
          <button onclick="AppRouter.renderModule('home')"
                  class="btn btn-edit text-sm">← Volver al Dashboard</button>
        </div>`;
    }
  }

  // ─── Render módulo ───────────────────────────────────────────────────────────
  async function renderModule(moduleName) {
    moduleName = moduleName || 'home';
    const rol  = window.RBAC ? RBAC.rol() : '';

    // Auditor siempre empieza en auditoria
    if (rol === 'auditor' && moduleName === 'home') moduleName = 'auditoria';

    let modDef = MODULES[moduleName];
    if (!modDef) {
      moduleName = (rol === 'auditor') ? 'auditoria' : 'home';
      modDef     = MODULES[moduleName];
    }

    // Validar acceso por rol
    if (modDef.roles && rol && !modDef.roles.includes(rol)) {
      moduleName = (rol === 'auditor') ? 'auditoria' : 'home';
      modDef     = MODULES[moduleName];
    }

    setQueryModule(moduleName);
    updateSidebarActive(moduleName);
    await loadView(modDef.file);
  }

  // ─── Marcar enlace activo en sidebar (v1.5: clases del modelo nuevo) ─────────
  function updateSidebarActive(activeModule) {
    // 1. Limpiar todos los estados activos anteriores
    document.querySelectorAll('.nav-item.is-active').forEach(el => el.classList.remove('is-active'));
    document.querySelectorAll('.nav-sublink.is-active').forEach(el => el.classList.remove('is-active'));

    // 2. Buscar el link con data-module que coincida
    const allLinks = document.querySelectorAll('[data-module]');
    allLinks.forEach(link => {
      if (link.dataset.module !== activeModule) return;

      // Es un nav-link directo (top-level)
      if (link.classList.contains('nav-link') || link.tagName === 'A') {
        if (link.classList.contains('nav-item')) {
          link.classList.add('is-active');
        } else {
          // Es un nav-sublink
          link.classList.add('is-active');
          // Abrir el acordeón padre si está cerrado
          const subList = link.closest('.submenu');
          if (subList) {
            const parentBtn = document.querySelector(`[data-target="${subList.id}"]`);
            if (parentBtn && !parentBtn.classList.contains('is-expanded')) {
              subList.style.maxHeight = subList.scrollHeight + 'px';
              subList.classList.add('is-open');
              parentBtn.classList.add('is-expanded');
              parentBtn.setAttribute('aria-expanded', 'true');
            }
          }
        }
      }
    });
  }

  // ─── Inicialización ──────────────────────────────────────────────────────────
  let layoutLoaded = false;

  async function init() {
    if (!layoutLoaded) {
      await Promise.all([
        loadComponent('topbar-container', 'topbar.html'),
        loadComponent('sidebar-container', 'sidebar.html'),
      ]);
      layoutLoaded = true;

      if (window.RBAC && typeof RBAC.aplicarUI === 'function') RBAC.aplicarUI();

      // Hermes widget visible
      document.getElementById('hermes-widget-container')?.classList.remove('hidden');
    }

    await renderModule(getQueryModule());
    _firstLoad = false;

    window.addEventListener('popstate', e => {
      renderModule(e.state?.module || getQueryModule());
    });

    // Delegación de eventos global en body
    document.body.addEventListener('click', e => {
      // En construcción (data-in-construction)
      const constLink = e.target.closest('[data-in-construction="true"]');
      if (constLink) {
        e.preventDefault();
        showConstructionModal();
        return;
      }

      // Navegación SPA - data-module (nuevo sistema UNIFICADO)
      const navLink = e.target.closest('[data-module]');
      if (navLink && !navLink.closest('.argos-modal-backdrop')) {
        e.preventDefault();
        renderModule(navLink.dataset.module);
        // En mobile: cerrar sidebar al navegar
        document.getElementById('sidebar')?.classList.add('-translate-x-full');
        document.getElementById('sidebar-overlay')?.classList.add('hidden');
        document.getElementById('sidebar-overlay')?.classList.remove('is-visible');
        return;
      }

      // Mantener compatibilidad con data-nav-module (legado)
      const legacyLink = e.target.closest('[data-nav-module]');
      if (legacyLink) {
        e.preventDefault();
        renderModule(legacyLink.dataset.navModule);
      }
    });
  }

  // ─── Modal "En Construcción" (con CSS vars) ───────────────────────────────────
  function showConstructionModal() {
    document.getElementById('construction-modal')?.remove();
    const modal = document.createElement('div');
    modal.id = 'construction-modal';
    modal.className = 'fixed inset-0 z-[999] flex items-center justify-center';
    modal.innerHTML = `
      <div class="absolute inset-0 bg-black/70 backdrop-blur-sm"
           onclick="document.getElementById('construction-modal').remove()"></div>
      <div class="relative rounded-2xl p-8 max-w-sm w-full mx-4 text-center shadow-2xl argos-modal fade-in">
        <div class="text-5xl mb-4">🚧</div>
        <h3 class="font-rajdhani text-2xl font-bold mb-2" style="color:var(--texto)">En Construcción</h3>
        <p class="text-sm leading-relaxed mb-6" style="color:var(--dim)">
          Este módulo está en desarrollo activo. Estará disponible en la próxima versión de ARGOS - SiViA.
        </p>
        <div class="font-mono text-[9px] tracking-widest uppercase mb-6" style="color:var(--rojo)">
          Próximamente · ARGOS v2.0
        </div>
        <button onclick="document.getElementById('construction-modal').remove()"
                class="btn btn-primary">Entendido</button>
      </div>`;
    document.body.appendChild(modal);
  }

  return { init, renderModule, showConstructionModal };
})();

window.AppRouter = AppRouter;
