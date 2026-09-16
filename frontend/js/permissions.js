/**
 * ARGOS - SiViA · Permissions Matrix
 * Módulo: Permisos y Accesos (05.02)
 * Archivo separado para evitar conflictos con dashboard.js
 */

(function() {
  'use strict';

  // ── Datos ────────────────────────────────────────────
  var ROLES = ['admin','supervisor','operador','analista','tecnico','auditor'];

  var ROLE_COLORS = {
    admin:'#a371f7', supervisor:'#38bdf8', operador:'#34d399',
    analista:'#fbbf24', tecnico:'#f97316', auditor:'#94a3b8'
  };

  var ROLE_LABELS = {
    admin:'Admin', supervisor:'Supervisor', operador:'Operador',
    analista:'Analista', tecnico:'Técnico', auditor:'Auditor'
  };

  var MODULES = [
    { id:'monitoreo', label:'📡 Monitoreo en Tiempo Real',
      perms:{ admin:'locked', supervisor:true,  operador:true,  analista:false, tecnico:true,  auditor:false }},
    { id:'alertas',   label:'🔔 Alertas y Eventos',
      perms:{ admin:'locked', supervisor:true,  operador:true,  analista:false, tecnico:false, auditor:false }},
    { id:'pose',      label:'🏃 Detección de Pose',
      perms:{ admin:'locked', supervisor:true,  operador:true,  analista:false, tecnico:true,  auditor:false }},
    { id:'analisis',  label:'📊 Análisis e Informes',
      perms:{ admin:'locked', supervisor:true,  operador:false, analista:true,  tecnico:false, auditor:true  }},
    { id:'ia',        label:'🧠 Gestión de IA / Modelo',
      perms:{ admin:'locked', supervisor:false, operador:false, analista:true,  tecnico:true,  auditor:false }},
    { id:'infra',     label:'🏗️ Infraestructura',
      perms:{ admin:'locked', supervisor:false, operador:false, analista:false, tecnico:true,  auditor:false }},
    { id:'usuarios',  label:'👤 Usuarios y Roles',
      perms:{ admin:'locked', supervisor:false, operador:false, analista:false, tecnico:false, auditor:true  }},
    { id:'config',    label:'⚙️ Configuración del Sistema',
      perms:{ admin:'locked', supervisor:false, operador:false, analista:false, tecnico:true,  auditor:false }}
  ];

  // Deep clone para comparar cambios
  var saved   = JSON.parse(JSON.stringify(MODULES));
  var current = JSON.parse(JSON.stringify(MODULES));

  // ── Helpers ──────────────────────────────────────────
  function countChanges() {
    var n = 0;
    current.forEach(function(mod, i) {
      ROLES.forEach(function(rol) {
        if (saved[i].perms[rol] !== 'locked' &&
            current[i].perms[rol] !== saved[i].perms[rol]) n++;
      });
    });
    return n;
  }

  function updateActionBar() {
    var n     = countChanges();
    var btn   = document.getElementById('pm-save-btn');
    var badge = document.getElementById('pm-changed-badge');
    var count = document.getElementById('pm-changed-count');
    if (!btn) return;
    if (n > 0) {
      btn.disabled       = false;
      btn.style.opacity  = '1';
      btn.style.cursor   = 'pointer';
      if (badge) { badge.style.display = 'inline-block'; }
      if (count) { count.textContent   = n; }
    } else {
      btn.disabled       = true;
      btn.style.opacity  = '.4';
      btn.style.cursor   = 'not-allowed';
      if (badge) { badge.style.display = 'none'; }
    }
  }

  function showToast(msg) {
    var t = document.getElementById('pm-toast');
    if (!t) return;
    t.textContent    = msg;
    t.style.display  = 'block';
    t.style.animation = 'ugModalIn .2s ease';
    clearTimeout(t._timer);
    t._timer = setTimeout(function() { t.style.display = 'none'; }, 3200);
  }

  // ── Render stats cards ───────────────────────────────
  function renderStats() {
    var grid = document.getElementById('pm-stats-grid');
    if (!grid) return;
    grid.innerHTML = ROLES.map(function(rol) {
      var count = current.filter(function(m) {
        return m.perms[rol] === true || m.perms[rol] === 'locked';
      }).length;
      return '<div style="background:var(--panel-bg,#0d1117);border:1px solid var(--border,#21262d);border-radius:8px;padding:12px 14px;">' +
        '<div style="font-size:10px;color:' + ROLE_COLORS[rol] + ';font-family:monospace;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">' + ROLE_LABELS[rol] + '</div>' +
        '<div style="font-size:22px;font-weight:700;color:' + ROLE_COLORS[rol] + ';font-family:monospace;">' + count + '</div>' +
        '<div style="font-size:10px;color:#6b7280;font-family:monospace;">de ' + MODULES.length + ' módulos</div>' +
      '</div>';
    }).join('');
  }

  // ── Render main matrix ───────────────────────────────
  function render() {
    var tbody = document.getElementById('pm-tbody');
    if (!tbody) return;

    renderStats();

    var rows = current.map(function(mod, modIdx) {
      var cells = ROLES.map(function(rol) {
        var val       = mod.perms[rol];
        var savedVal  = saved[modIdx].perms[rol];
        var isPending = val !== savedVal;

        if (val === 'locked') {
          return '<td style="text-align:center;padding:10px 6px;">' +
            '<span class="pm-chip pm-chip-locked">✓ Siempre</span></td>';
        }

        var chipCls = 'pm-chip ' + (val ? 'pm-chip-on' : 'pm-chip-off') +
                      (isPending ? (val ? ' pm-pending-on' : ' pm-pending-off') : '');
        var chipTxt = val ? '✓ Sí' : '- No';

        return '<td class="pm-cell" data-mod="' + modIdx + '" data-rol="' + rol + '" ' +
          'style="text-align:center;padding:10px 6px;cursor:pointer;" ' +
          'onclick="window.pmToggle(' + modIdx + ',\'' + rol + '\')">' +
          '<span class="' + chipCls + '">' + chipTxt + '</span></td>';
      }).join('');

      return '<tr class="pm-mod-row"><td class="pm-mod-label" style="padding:10px 12px;font-size:13px;font-weight:700;">' +
        mod.label + '</td>' + cells + '</tr>';
    }).join('');

    tbody.innerHTML = rows;
    updateActionBar();
  }

  // ── Public API (window.*) ────────────────────────────
  window.pmRender = render;

  window.pmToggle = function(modIdx, rol) {
    if (!current[modIdx]) return;
    if (current[modIdx].perms[rol] === 'locked') return;
    current[modIdx].perms[rol] = !current[modIdx].perms[rol];
    render();
  };

  window.pmGuardar = function() {
    var n = countChanges();
    if (n === 0) return;
    saved   = JSON.parse(JSON.stringify(current));
    render();
    showToast('✅ ' + n + ' cambio(s) guardado(s) correctamente.');
  };

  window.pmDescartar = function() {
    var n = countChanges();
    if (n === 0) { showToast('ℹ️ No hay cambios pendientes.'); return; }
    current = JSON.parse(JSON.stringify(saved));
    render();
    showToast('↩ Cambios descartados.');
  };

  // ── Hook showSub - espera a que dashboard.js también se cargue ──
  // Usamos DOMContentLoaded para garantizar que todos los scripts
  // ya estén parseados antes de envolver showSub.
  document.addEventListener('DOMContentLoaded', function() {
    // Retry hasta que showSub esté definido (dashboard.js puede llegar tarde)
    var attempts = 0;
    var interval = setInterval(function() {
      attempts++;
      if (typeof window.showSub === 'function') {
        clearInterval(interval);
        var _prev = window.showSub;
        window.showSub = function(menu, sub) {
          _prev(menu, sub);
          if (menu === 'usuarios' && sub === 'permisos') {
            setTimeout(render, 80);
          }
        };
        console.log('[permissions.js] showSub hook installed after', attempts, 'attempt(s)');
      } else if (attempts > 50) {
        clearInterval(interval);
        console.warn('[permissions.js] showSub never defined - hook not installed');
      }
    }, 50);
  });

})();
