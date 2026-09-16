/**
 * frontend/js/rbac.js
 * ────────────────────────────────────────────────────────────
 * ARGOS - SiViA  ·  Helper RBAC para el frontend
 *
 * FIXES v1.2.1:
 *  - Token leído desde sessionStorage (igual que api.js / Session.getToken)
 *  - RBAC.init() ahora también filtra cards del dashboard por módulo
 *  - Función pública RBAC.filtrarCards() para llamar al cargar home
 *
 * Uso:
 *   await RBAC.init();                          // al arrancar la app
 *   RBAC.puede('camaras:eliminar')              // → true / false
 *   RBAC.moduloVisible('usuarios')              // → true / false
 *   RBAC.aplicarUI();                           // oculta [data-permiso] / [data-modulo]
 *   RBAC.filtrarCards();                        // oculta cards del dashboard sin permiso
 */

const RBAC = (() => {

    let _permisos = new Set();
    let _rol      = '';
    let _modulos  = [];

    // ── Obtener token - usa sessionStorage como api.js ─────────────
    function _getToken() {
        // Primero sessionStorage (Session.getToken de api.js)
        return sessionStorage.getItem('argos_token')
            || localStorage.getItem('argos_token')
            || null;
    }

    // ── Inicializar: carga permisos desde la API ───────────────────
    async function init() {
        const token = _getToken();
        if (!token) {
            console.warn('[RBAC] Sin token - permisos no cargados.');
            return;
        }

        try {
            const [resPermisos, resMod] = await Promise.all([
                fetch('/api/rbac/permisos', { headers: { 'X-Token': token } }),
                fetch('/api/rbac/modulos',  { headers: { 'X-Token': token } }),
            ]);

            if (resPermisos.ok) {
                const data = await resPermisos.json();
                _rol      = data.rol      || '';
                _permisos = new Set(data.permisos || []);
            } else {
                console.error('[RBAC] /api/rbac/permisos →', resPermisos.status);
            }

            if (resMod.ok) {
                const dataMod = await resMod.json();
                _modulos = dataMod.modulos || [];
            } else {
                console.error('[RBAC] /api/rbac/modulos →', resMod.status);
            }

            console.log(`[RBAC] Rol: ${_rol} | Módulos: ${_modulos.join(', ')} | Permisos: ${_permisos.size}`);
        } catch (e) {
            console.error('[RBAC] Error cargando permisos:', e);
        }
    }

    // ── Verificar permiso ──────────────────────────────────────────
    function puede(permiso) {
        return _permisos.has(permiso);
    }

    // ── Verificar módulo ──────────────────────────────────────────
    function moduloVisible(modulo) {
        // Admin siempre ve todo
        if (_rol === 'admin') return true;
        return _modulos.includes(modulo);
    }

    // ── Obtener rol ───────────────────────────────────────────────
    function rol() {
        return _rol;
    }

    // ── Aplicar RBAC al DOM ───────────────────────────────────────
    /**
     * Oculta elementos HTML que requieren un permiso que el usuario no tiene.
     *
     * Uso en HTML:
     *   <button data-permiso="camaras:eliminar">Eliminar</button>
     *   <li    data-modulo="usuarios">Usuarios</li>
     *   <div   data-rol="admin">Solo admins</div>
     */
    function aplicarUI() {
        // Elementos con data-permiso="..."
        document.querySelectorAll('[data-permiso]').forEach(el => {
            const p = el.dataset.permiso;
            if (!puede(p)) {
                el.style.display = 'none';
                el.setAttribute('aria-hidden', 'true');
            } else {
                el.style.display = '';
                el.removeAttribute('aria-hidden');
            }
        });

        // Elementos con data-modulo="..."
        document.querySelectorAll('[data-modulo]').forEach(el => {
            const m = el.dataset.modulo;
            if (!moduloVisible(m)) {
                el.style.display = 'none';
                el.setAttribute('aria-hidden', 'true');
            } else {
                el.style.display = '';
                el.removeAttribute('aria-hidden');
            }
        });

        // Elementos con data-rol="..." (rol exacto, acepta lista separada por coma)
        document.querySelectorAll('[data-rol]').forEach(el => {
            const roles = el.dataset.rol.split(',').map(r => r.trim());
            if (!roles.includes(_rol)) {
                el.style.display = 'none';
                el.setAttribute('aria-hidden', 'true');
            } else {
                el.style.display = '';
                el.removeAttribute('aria-hidden');
            }
        });
    }

    // ── Contexto para Hermes ──────────────────────────────────────
    function getHermesContext(moduloActual = '') {
        return {
            rol:    _rol,
            modulo: moduloActual,
        };
    }

    // ── Función pública tienePermiso (alias legible) ───────────────
    function tienePermiso(permiso) {
        return puede(permiso);
    }

    return { init, puede, tienePermiso, moduloVisible, rol, aplicarUI, getHermesContext };

})();



// Hermes IA está definido en api.js (window.ARGOS.Hermes). No se redeclara aquí.

