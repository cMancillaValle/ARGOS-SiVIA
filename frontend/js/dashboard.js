/**
 * ARGOS - SiViA · Dashboard Controller
 * ──────────────────────────────────────
 * Conecta todos los paneles del dashboard con la API backend.
 */

// ══════════════════════════════════════════════════════
//  INICIALIZACIÓN - sin llamadas de red, lee sessionStorage
// ══════════════════════════════════════════════════════
// ── initDashboard es async para poder await RBAC.init() ──────────
(async function initDashboard() {

  const token = sessionStorage.getItem('argos_token');
  let user = null;
  try { user = JSON.parse(sessionStorage.getItem('argos_user')); } catch(e) {}

  if (!token || !user) {
    window.location.replace('login.html');
    return;
  }

  function setEl(id, v) { var e = document.getElementById(id); if (e && v !== undefined && v !== null) e.textContent = v; }

  // ── Topbar ────────────────────────────────────────
  setEl('topbar-avatar',     (user.username || '??').substring(0, 2).toUpperCase());
  setEl('topbar-username',   user.nombre || user.username);
  setEl('topbar-role-label', (user.rol || '').toUpperCase());

  window.currentUser = user;
  window.currentRole = user.rol;

  // ── Sidebar por rol (función definida en dashboard.html inline script) ──
  // Se intenta inmediatamente y también en DOMContentLoaded por si el inline
  // script todavía no fue parseado (orden de carga de scripts externos vs inline)
  function trySidebarRole() {
    if (typeof applySidebarRole === 'function') {
      applySidebarRole(user.rol);
      return true;
    }
    return false;
  }
  if (!trySidebarRole()) {
    document.addEventListener('DOMContentLoaded', trySidebarRole);
  }

  // ── RBAC: cargar permisos desde API y aplicar al DOM ─────────
  // Se hace ANTES de showHome() para que las cards ya estén filtradas
  // cuando aparezcan en pantalla (sin parpadeo).
  if (typeof RBAC !== 'undefined') {
    try {
      await RBAC.init();
    } catch(e) {
      console.warn('[dashboard] RBAC.init() falló:', e);
    }
  }

  // ── Settings drawer ───────────────────────────────────────────
  window.addEventListener('load', function() {
    var r        = (typeof ROLES !== 'undefined' && ROLES[user.rol]) ? ROLES[user.rol] : null;
    var initials = (user.username || '??').substring(0, 2).toUpperCase();

    setEl('settings-avatar',      initials);
    setEl('settings-username',    user.nombre || user.username || '-');
    setEl('settings-email',       user.email  || '');

    if (r) {
      setEl('settings-role-badge',  r.label);
      setEl('settings-role-badge2', r.short);
      var b1 = document.getElementById('settings-role-badge');
      var b2 = document.getElementById('settings-role-badge2');
      if (b1) b1.className = 'badge-role ' + r.badge;
      if (b2) b2.className = 'badge-role ' + r.badge;
    } else {
      setEl('settings-role-badge',  (user.rol || '-').toUpperCase());
      setEl('settings-role-badge2', (user.rol || '-').toUpperCase());
    }
  });

  var fab = document.getElementById('hermes-fab');
  if (fab) fab.style.display = 'flex';

  try {
    var t = localStorage.getItem('sivia-theme');
    if (t && typeof setTheme === 'function') setTheme(t);
  } catch(e) {}

  // ── Mostrar home y aplicar filtros RBAC ──────────────────────
  if (typeof showHome === 'function') showHome();
  if (typeof RBAC !== 'undefined') {
    RBAC.aplicarUI();   // filtra cards, sidebar data-modulo, data-permiso, data-rol
  }

  loadDashboardStats();

  window.cerrarSesion = async function() {
    try { await ARGOS.Auth.logout(); } catch(e) {}
    sessionStorage.clear();
    window.location.replace('login.html');
  };

})();


// ══════════════════════════════════════════════════════
//  STATS DEL PANEL PRINCIPAL
// ══════════════════════════════════════════════════════
async function loadDashboardStats() {
  try {
    const [stats, camStats] = await Promise.all([ARGOS.Stats.general(), ARGOS.Camaras.stats()]);
    const s = (id, v) => { const e = document.getElementById(id); if(e) e.textContent = v; };
    s('dash-stat-camaras', camStats.activas ?? stats.camaras?.activas ?? '-');
    s('dash-stat-alertas', stats.eventos?.total ?? '-');
    if (stats.eventos?.pendientes > 0) {
      const el = document.querySelector('.dash-status-item:nth-child(3)');
      if (el) el.innerHTML = `<div class="dash-status-dot yellow"></div><span>${stats.eventos.pendientes} alertas pendientes</span>`;
    }
    const sessEl = document.getElementById('dash-session-info');
    if (sessEl && window.currentUser)
      sessEl.textContent = window.currentUser.username.toUpperCase() + ' · ' + (window.currentUser.rol||'').toUpperCase();
  } catch(e) {}
}


// ══════════════════════════════════════════════════════
//  HOOK: showSub → carga datos reales al abrir panel
// ══════════════════════════════════════════════════════
const _origShowSub = window.showSub;
window.showSub = function(menu, sub) {
  if (typeof _origShowSub === 'function') _origShowSub(menu, sub);
  const loaders = {
    'monitoreo-cam':         loadCamarasPanel,
    'monitoreo-alertas':     loadAlertasPanel,
    'usuarios-gestion':      loadUsuariosPanel,
    'usuarios-permisos':     loadPermisosPanel,
    'usuarios-auditoria':    loadAuditoriaPanel,
    'config-notificaciones': loadNotificacionesPanel,
    'config-sistema':        loadSistemaPanel,
  };
  const fn = loaders[`${menu}-${sub}`];
  if (fn) setTimeout(fn, 60);
  // Also trigger UG render for gestion panel
  if (menu === 'usuarios' && sub === 'gestion' && typeof window.ugRender === 'function') {
    setTimeout(window.ugRender, 80);
  }
};


// ══════════════════════════════════════════════════════
//  UTILIDADES COMPARTIDAS
// ══════════════════════════════════════════════════════
function panelLoading(containerId, msg) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div style="padding:32px;text-align:center;color:var(--texto-dim);
    font-family:'Share Tech Mono',monospace;font-size:11px;letter-spacing:1px">
    <div style="font-size:24px;margin-bottom:8px;animation:spin 1s linear infinite;display:inline-block">⟳</div>
    <div>${msg||'Cargando...'}</div></div>`;
}

function statsBar(items) {
  return `<div class="stats-grid" style="margin-bottom:20px">${items.map(([lbl,val,color]) =>
    `<div class="stat-card"><div class="stat-label">${lbl}</div>
     <div class="stat-value ${color||''}">${val}</div></div>`).join('')}</div>`;
}

function tableWrap(headCols, rows) {
  const thStyle = `padding:9px 10px;font-family:'Share Tech Mono',monospace;font-size:9px;
    letter-spacing:1.5px;color:var(--rojo);text-align:left;border-bottom:1px solid var(--rojo)`;
  return `<div class="info-block" style="overflow-x:auto;padding:0">
    <table style="width:100%;border-collapse:collapse">
      <thead><tr>${headCols.map(h=>`<th style="${thStyle}">${h}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

function tdS(extra) {
  return `style="padding:10px;font-size:12px;border-bottom:1px solid var(--linea);${extra||''}"`;
}

function replaceStaticPanelContent(panelId, newHtml) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  const header = panel.querySelector('.panel-header');
  if (!header) return;
  let next = header.nextElementSibling;
  while (next) { const r = next; next = next.nextElementSibling; r.remove(); }
  const div = document.createElement('div');
  div.innerHTML = newHtml;
  panel.appendChild(div);
}


// ══════════════════════════════════════════════════════
//  PANEL: CÁMARAS ACTIVAS
// ══════════════════════════════════════════════════════
async function loadCamarasPanel() {
  const id = 'panel-camaras-content';
  panelLoading(id, 'Cargando cámaras...');
  const [data, st] = await Promise.all([ARGOS.Camaras.listar(), ARGOS.Camaras.stats()]);
  const rows = (data.camaras||[]).map(c=>`<tr>
    <td ${tdS('font-family:Share Tech Mono,monospace;font-size:11px;color:var(--amarillo)')}>${c.codigo}</td>
    <td ${tdS('')}>${c.estacion}</td>
    <td ${tdS('color:var(--texto-dim);font-size:11px')}>${c.ubicacion}</td>
    <td ${tdS('')}>${ARGOS.UI.badgeCamara(c.estado)}</td>
    <td ${tdS('font-family:Share Tech Mono,monospace;font-size:10px;color:var(--texto-dim)')}>${c.ip||'-'}</td>
    <td ${tdS('font-size:11px;color:var(--texto-dim)')}>${c.fps} FPS · ${c.resolucion}</td>
  </tr>`).join('');
  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = statsBar([
    ['Total',st.total||0,''],['Activas',st.activas||0,'green'],
    ['Offline',st.offline||0,'red'],['Mantenimiento',st.mantenimiento||0,'yellow'],
  ]) + tableWrap(['CÓDIGO','ESTACIÓN','UBICACIÓN','ESTADO','IP','CONFIG'], rows);
}


// ══════════════════════════════════════════════════════
//  PANEL: ALERTAS Y EVENTOS
// ══════════════════════════════════════════════════════
async function loadAlertasPanel() {
  const id = 'panel-alertas-content';
  panelLoading(id, 'Cargando eventos...');
  const data = await ARGOS.Eventos.listar({ limite: 40 });
  renderAlertasList(id, data.eventos||[], data.total||0);
}

function renderAlertasList(id, eventos, total) {
  const canReview = ['admin','supervisor','operador'].includes(window.currentRole);
  const rows = eventos.map(e=>`
    <div class="alert-row" ${canReview?`onclick="revisarEvento(${e.id})" style="cursor:pointer"`:''}>
      <div class="alert-ico">${e.tipo==='evasion'?'🚨':e.tipo==='intrusion'?'⚠️':'📋'}</div>
      <div class="alert-txt">
        <strong>${e.camara_codigo} · ${e.estacion}</strong>
        <span>${e.ubicacion} · ${e.tipo.toUpperCase()} · Conf: ${Math.round(e.confianza*100)}%</span>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
        ${ARGOS.UI.badgeEstado(e.estado)}
        <div class="alert-time">${ARGOS.UI.formatFecha(e.detectado_en)}</div>
      </div>
    </div>`).join('') || '<div style="padding:20px;text-align:center;color:var(--texto-dim)">Sin eventos.</div>';

  const el = document.getElementById(id);
  if (!el) return;
  el.innerHTML = `
    <div class="action-bar">
      <button class="btn-action primary" onclick="loadAlertasPanel()">🔄 Actualizar</button>
      <button class="btn-action" onclick="filtrarEventos('')">Todos (${total})</button>
      <button class="btn-action" onclick="filtrarEventos('pendiente')">⏳ Pendientes</button>
      <button class="btn-action" onclick="filtrarEventos('confirmado')">✅ Confirmados</button>
      <button class="btn-action" onclick="filtrarEventos('descartado')">❌ Descartados</button>
    </div>
    <div id="alertas-list">${rows}</div>`;
}

async function filtrarEventos(estado) {
  const list = document.getElementById('alertas-list');
  if (!list) return;
  list.innerHTML = '<div style="padding:20px;color:var(--texto-dim)">Filtrando...</div>';
  const data = await ARGOS.Eventos.listar(estado ? {estado,limite:40} : {limite:40});
  const canReview = ['admin','supervisor','operador'].includes(window.currentRole);
  list.innerHTML = (data.eventos||[]).map(e=>`
    <div class="alert-row" ${canReview?`onclick="revisarEvento(${e.id})" style="cursor:pointer"`:''}>
      <div class="alert-ico">${e.tipo==='evasion'?'🚨':'⚠️'}</div>
      <div class="alert-txt">
        <strong>${e.camara_codigo} · ${e.estacion}</strong>
        <span>${e.tipo.toUpperCase()} · Conf: ${Math.round(e.confianza*100)}%</span>
      </div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
        ${ARGOS.UI.badgeEstado(e.estado)}
        <div class="alert-time">${ARGOS.UI.formatFecha(e.detectado_en)}</div>
      </div>
    </div>`).join('') || '<div style="padding:20px;text-align:center;color:var(--texto-dim)">Sin resultados.</div>';
}

async function revisarEvento(id) {
  if (!['admin','supervisor','operador'].includes(window.currentRole)) {
    ARGOS.UI.toast('Sin permiso para revisar eventos.','error'); return;
  }
  const accion = confirm('¿Confirmar evasión?\n\nAceptar = Confirmar   /   Cancelar = Descartar');
  const estado = accion ? 'confirmado' : 'descartado';
  const res = await ARGOS.Eventos.actualizarEstado(id, estado, accion?'Confirmado por operador':'Descartado por operador');
  if (res?.ok) { ARGOS.UI.toast(`Evento ${estado}.`, accion?'success':'info'); loadAlertasPanel(); }
  else ARGOS.UI.toast(res?.data?.error||'Error.','error');
}


// ══════════════════════════════════════════════════════
//  PANEL: GESTIÓN DE OPERADORES
// ══════════════════════════════════════════════════════
const ROLE_COLORS = {
  admin:'var(--rojo)',supervisor:'var(--amarillo)',operador:'var(--verde)',
  analista:'var(--azul)',tecnico:'var(--amarillo)',auditor:'var(--texto-dim)',
};

async function loadUsuariosPanel() {
  // La gestión de usuarios está manejada por ugRender() (users.js / dashboard.html)
  if (typeof window.ugRender === 'function') {
    window.ugRender();
  }
}





// ══════════════════════════════════════════════════════
//  PANEL: PERMISOS Y ACCESOS
// ══════════════════════════════════════════════════════
async function loadPermisosPanel() {
  // La matriz interactiva está manejada por pmRender() en dashboard.html
  if (typeof window.pmRender === 'function') {
    window.pmRender();
  }
}


// ══════════════════════════════════════════════════════
//  PANEL: AUDITORÍA DEL SISTEMA
// ══════════════════════════════════════════════════════
async function loadAuditoriaPanel() {
  const ICONS={LOGIN:'🔑',LOGOUT:'🚪',CAMARA_CREADA:'📷',CAMARA_ACTUALIZADA:'✏️',CAMARA_ELIMINADA:'🗑️',
    USUARIO_CREADO:'👤',USUARIO_ACTUALIZADO:'✏️',USUARIO_DESACTIVADO:'🔒',
    PASSWORD_CAMBIADA:'🔐',EVENTO_CONFIRMADO:'✅',EVENTO_DESCARTADO:'❌'};

  const id='panel-auditoria-content';
  const container=document.getElementById(id);
  if (container) { panelLoading(id,'Cargando auditoría...'); }

  const data=await ARGOS.Stats.auditoria(80);
  const registros=data.registros||[];

  const rows=registros.map(r=>`
    <div style="display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid var(--linea)">
      <div style="font-size:18px;flex-shrink:0">${ICONS[r.accion]||'📋'}</div>
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span style="font-family:Rajdhani,sans-serif;font-size:13px;font-weight:600">${r.accion}</span>
          <span style="font-family:Share Tech Mono,monospace;font-size:9px;color:var(--amarillo);
            background:rgba(255,200,0,0.08);padding:2px 7px;border-radius:3px">${r.rol||'sistema'}</span>
        </div>
        <div style="font-size:11px;color:var(--texto-dim);margin-top:2px">${r.nombre||'Sistema'} · ${r.detalle||''}</div>
      </div>
      <div style="flex-shrink:0;text-align:right">
        <div style="font-family:Share Tech Mono,monospace;font-size:9px;color:var(--texto-dim)">${ARGOS.UI.formatFecha(r.fecha)}</div>
        <div style="font-family:Share Tech Mono,monospace;font-size:9px;color:rgba(122,147,178,0.5)">${r.ip_origen||'-'}</div>
      </div>
    </div>`).join('')||'<div style="padding:20px;text-align:center;color:var(--texto-dim)">Sin registros.</div>';

  const html=`
    <div class="action-bar">
      <button class="btn-action primary" onclick="loadAuditoriaPanel()">🔄 Actualizar</button>
    </div>
    ${statsBar([
      ['Registros',registros.length,'blue'],
      ['Logins',registros.filter(r=>r.accion==='LOGIN').length,'green'],
      ['Cambios config',registros.filter(r=>r.accion.includes('ACTUALIZ')||r.accion.includes('CREADA')).length,'yellow'],
      ['Eventos revisados',registros.filter(r=>r.accion.includes('EVENTO')).length,''],
    ])}
    <div class="info-block">${rows}</div>`;

  if (container) { container.innerHTML=html; }
  else { replaceStaticPanelContent('sub-usuarios-auditoria',html); }
}


// ══════════════════════════════════════════════════════
//  PANEL: NOTIFICACIONES Y ALERTAS
// ══════════════════════════════════════════════════════
const NOTIF_KEY='argos_notif_config';

function getNotifConfig() {
  try { const s=localStorage.getItem(NOTIF_KEY); if(s) return JSON.parse(s); } catch(e){}
  return {alertas_criticas:true,sonido:true,popup:true,email:false,
    frecuencia:'5',umbral_confianza:'75',email_destino:'',horario_inicio:'05:00',horario_fin:'23:30'};
}

function toggle(id,checked) {
  return `<label class="toggle"><input type="checkbox" id="${id}" ${checked?'checked':''}><div class="toggle-track"></div></label>`;
}

window.saveNotifConfig=function() {
  const cfg={
    alertas_criticas:document.getElementById('nc-criticas')?.checked??true,
    sonido:document.getElementById('nc-sonido')?.checked??true,
    popup:document.getElementById('nc-popup')?.checked??true,
    email:document.getElementById('nc-email-toggle')?.checked??false,
    frecuencia:document.getElementById('nc-frecuencia')?.value??'5',
    umbral_confianza:document.getElementById('nc-umbral')?.value??'75',
    email_destino:document.getElementById('nc-email-addr')?.value??'',
    horario_inicio:document.getElementById('nc-inicio')?.value??'05:00',
    horario_fin:document.getElementById('nc-fin')?.value??'23:30',
  };
  try{localStorage.setItem(NOTIF_KEY,JSON.stringify(cfg));}catch(e){}
  ARGOS.UI.toast('Configuración de notificaciones guardada.','success');
};

window.probarNotificacion=function() {
  ARGOS.UI.toast('🧪 Notificación de prueba enviada correctamente.','success',4000);
};

async function loadNotificacionesPanel() {
  const cfg=getNotifConfig();
  const stats=await ARGOS.Stats.general().catch(()=>({}));

  replaceStaticPanelContent('sub-config-notificaciones',`
    ${statsBar([
      ['Pendientes',stats.eventos?.pendientes??0,stats.eventos?.pendientes>0?'red':'green'],
      ['Detectadas hoy',stats.eventos?.hoy??0,'yellow'],
      ['Total procesadas',stats.eventos?.total??0,'blue'],
      ['Precisión modelo',stats.sistema?.precision_modelo?Math.round(stats.sistema.precision_modelo*100)+'%':'-','green'],
    ])}
    <div class="info-block">
      <h3>Canales de notificación</h3>
      ${[
        ['nc-criticas',cfg.alertas_criticas,'🚨 Alertas críticas','Evasiones con alta confianza'],
        ['nc-sonido',cfg.sonido,'🔊 Sonido','Sonido al recibir alertas'],
        ['nc-popup',cfg.popup,'💬 Popup en pantalla','Ventanas flotantes de notificación'],
        ['nc-email-toggle',cfg.email,'📧 Notificaciones por correo','Resumen periódico'],
      ].map(([id,val,label,desc])=>`
        <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--linea)">
          <div><div style="font-size:13px">${label}</div><div style="font-size:10px;color:var(--texto-dim);margin-top:2px">${desc}</div></div>
          ${toggle(id,val)}
        </div>`).join('')}
      <div style="margin-top:10px">
        <label class="form-label">Email destino para notificaciones</label>
        <input id="nc-email-addr" class="form-input" type="email" value="${cfg.email_destino}" placeholder="operador@transmilenio.gov.co" style="max-width:360px">
      </div>
    </div>
    <div class="info-block">
      <h3>Parámetros de disparo</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div><label class="form-label">Frecuencia de agrupación</label>
          <select id="nc-frecuencia" class="form-select">
            ${[['1','Inmediata'],['5','Cada 5 min'],['15','Cada 15 min'],['60','Por hora']].map(
              ([v,l])=>`<option value="${v}" ${cfg.frecuencia===v?'selected':''}>${l}</option>`).join('')}
          </select></div>
        <div><label class="form-label">Umbral de confianza mínimo:
          <span id="nc-umbral-val" style="color:var(--amarillo)">${cfg.umbral_confianza}%</span></label>
          <input type="range" id="nc-umbral" class="form-slider" min="50" max="99" value="${cfg.umbral_confianza}"
            oninput="document.getElementById('nc-umbral-val').textContent=this.value+'%'">
          <p style="font-size:10px;color:var(--texto-dim);margin-top:4px">Solo se notifican detecciones con confianza ≥ umbral.</p>
        </div>
        <div><label class="form-label">Inicio horario activo</label>
          <input id="nc-inicio" class="form-input" type="time" value="${cfg.horario_inicio}"></div>
        <div><label class="form-label">Fin horario activo</label>
          <input id="nc-fin" class="form-input" type="time" value="${cfg.horario_fin}"></div>
      </div>
    </div>
    <div class="action-bar">
      <button class="btn-action primary" onclick="saveNotifConfig()">💾 Guardar configuración</button>
      <button class="btn-action" onclick="probarNotificacion()">🧪 Enviar prueba</button>
      <button class="btn-action" onclick="loadNotificacionesPanel()">🔄 Recargar</button>
    </div>`);
}


// ══════════════════════════════════════════════════════
//  PANEL: PARÁMETROS DEL SISTEMA
// ══════════════════════════════════════════════════════
const SISTEMA_KEY='argos_sistema_config';

function getSistemaConfig() {
  try{const s=localStorage.getItem(SISTEMA_KEY);if(s)return JSON.parse(s);}catch(e){}
  return {fps:'15',resolucion:'640',calidad:'720p',horario:'24_7',valle:'economico',
    ssd_dias:'30',hdd_dias:'90',incidentes:'1_anio'};
}

window.saveSistemaConfig=function() {
  const cfg={
    fps:document.getElementById('sc-fps')?.value??'15',
    resolucion:document.getElementById('sc-res')?.value??'640',
    calidad:document.getElementById('sc-calidad')?.value??'720p',
    horario:document.getElementById('sc-horario')?.value??'24_7',
    valle:document.getElementById('sc-valle')?.value??'economico',
    ssd_dias:document.getElementById('sc-ssd')?.value??'30',
    hdd_dias:document.getElementById('sc-hdd')?.value??'90',
    incidentes:document.getElementById('sc-incidentes')?.value??'1_anio',
  };
  try{localStorage.setItem(SISTEMA_KEY,JSON.stringify(cfg));}catch(e){}
  ARGOS.UI.toast('Parámetros del sistema guardados.','success');
};

window.resetSistemaConfig=function() {
  try{localStorage.removeItem(SISTEMA_KEY);}catch(e){}
  ARGOS.UI.toast('Configuración restablecida a valores por defecto.','info');
  loadSistemaPanel();
};

async function loadSistemaPanel() {
  const cfg=getSistemaConfig();
  const [stats,camStats]=await Promise.all([ARGOS.Stats.general().catch(()=>({})),ARGOS.Camaras.stats().catch(()=>({}))]);

  replaceStaticPanelContent('sub-config-sistema',`
    ${statsBar([
      ['Cámaras activas',camStats.activas??0,'blue'],
      ['Modo',cfg.horario==='24_7'?'24/7':'Programado','green'],
      ['FPS configurado',cfg.fps+' FPS','yellow'],
      ['Resolución',cfg.resolucion+'×'+cfg.resolucion+' px',''],
    ])}
    <div class="info-block">
      <h3>Captura de video</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div><label class="form-label">FPS de procesamiento</label>
          <select id="sc-fps" class="form-select">
            ${[['10','10 FPS - Económico'],['15','15 FPS - Balanceado (recomendado)'],['20','20 FPS - Alto rendimiento'],['30','30 FPS - Máxima calidad']].map(
              ([v,l])=>`<option value="${v}" ${cfg.fps===v?'selected':''}>${l}</option>`).join('')}
          </select>
          <p style="font-size:10px;color:var(--texto-dim);margin-top:4px">Mayor FPS = más precisión + más costo computacional.</p>
        </div>
        <div><label class="form-label">Resolución de entrada al modelo</label>
          <select id="sc-res" class="form-select">
            ${[['416','416×416 - Rápido'],['640','640×640 - Estándar YOLOv8'],['832','832×832 - Alta precisión'],['1024','1024×1024 - Máxima precisión']].map(
              ([v,l])=>`<option value="${v}" ${cfg.resolucion===v?'selected':''}>${l}</option>`).join('')}
          </select></div>
        <div><label class="form-label">Calidad de grabación</label>
          <select id="sc-calidad" class="form-select">
            ${[['480p','480p - Mínimo'],['720p','720p - Estándar'],['1080p','1080p - Alta calidad']].map(
              ([v,l])=>`<option value="${v}" ${cfg.calidad===v?'selected':''}>${l}</option>`).join('')}
          </select></div>
      </div>
    </div>
    <div class="info-block">
      <h3>Retención de datos</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div><label class="form-label">SSD (caliente): <span id="sc-ssd-val" style="color:var(--amarillo)">${cfg.ssd_dias} días</span></label>
          <input type="range" id="sc-ssd" class="form-slider" min="7" max="60" value="${cfg.ssd_dias}"
            oninput="document.getElementById('sc-ssd-val').textContent=this.value+' días'">
          <p style="font-size:10px;color:var(--texto-dim);margin-top:4px">Acceso rápido en disco SSD.</p>
        </div>
        <div><label class="form-label">HDD (frío): <span id="sc-hdd-val" style="color:var(--amarillo)">${cfg.hdd_dias} días</span></label>
          <input type="range" id="sc-hdd" class="form-slider" min="30" max="180" value="${cfg.hdd_dias}"
            oninput="document.getElementById('sc-hdd-val').textContent=this.value+' días'">
          <p style="font-size:10px;color:var(--texto-dim);margin-top:4px">Archivado para cumplimiento normativo.</p>
        </div>
        <div><label class="form-label">Retención de incidentes confirmados</label>
          <select id="sc-incidentes" class="form-select">
            ${[['6_meses','6 meses'],['1_anio','1 año (recomendado)'],['2_anios','2 años'],['permanente','Permanente']].map(
              ([v,l])=>`<option value="${v}" ${cfg.incidentes===v?'selected':''}>${l}</option>`).join('')}
          </select></div>
      </div>
    </div>
    <div class="info-block">
      <h3>Modo de operación</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div><label class="form-label">Horario de operación</label>
          <select id="sc-horario" class="form-select">
            ${[['24_7','24/7 - Continuo'],['tm','5:00 AM - 12:00 AM (Horario TM)'],['pico','Solo horas pico (6-9 AM, 5-8 PM)']].map(
              ([v,l])=>`<option value="${v}" ${cfg.horario===v?'selected':''}>${l}</option>`).join('')}
          </select></div>
        <div><label class="form-label">Procesamiento en horas valle</label>
          <select id="sc-valle" class="form-select">
            ${[['desactivado','Desactivado'],['economico','Modo económico (10 FPS)'],['estandar','Modo estándar (15 FPS)']].map(
              ([v,l])=>`<option value="${v}" ${cfg.valle===v?'selected':''}>${l}</option>`).join('')}
          </select></div>
      </div>
    </div>
    <div class="action-bar">
      <button class="btn-action primary" onclick="saveSistemaConfig()">💾 Guardar cambios</button>
      <button class="btn-action" onclick="resetSistemaConfig()">🔄 Restablecer predeterminados</button>
    </div>`);
}


// ══════════════════════════════════════════════════════
//  HERMES IA - backend real
// ══════════════════════════════════════════════════════
window.hermesEnviar = async function() {
  const input=document.getElementById('hermes-input');
  const text=(input?.value||'').trim();
  if (!text) return;
  const msgs=document.getElementById('hermes-msgs');
  const now=new Date().toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit'});
  const uDiv=document.createElement('div');
  uDiv.className='hermes-msg user';
  uDiv.innerHTML=`<div class="hermes-bubble">${text}</div><div class="hermes-msg-time">${now}</div>`;
  msgs.appendChild(uDiv);msgs.scrollTop=msgs.scrollHeight;
  if(input)input.value='';
  const qb=document.getElementById('hermes-quick');if(qb)qb.style.display='none';
  const thinking=document.createElement('div');
  thinking.className='hermes-msg bot';
  thinking.innerHTML='<div class="hermes-bubble"><em style="opacity:0.5">✦ consultando sistema...</em></div>';
  msgs.appendChild(thinking);msgs.scrollTop=msgs.scrollHeight;
  const respuesta=await ARGOS.Hermes.enviar(text);
  msgs.removeChild(thinking);
  const bDiv=document.createElement('div');
  bDiv.className='hermes-msg bot';
  const html=respuesta.replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>');
  bDiv.innerHTML=`<div class="hermes-bubble">${html}</div><div class="hermes-msg-time">${now}</div>`;
  msgs.appendChild(bDiv);msgs.scrollTop=msgs.scrollHeight;
};

window.hermesQuick=async function(key) {
  const labels={alertas:'Consultar alertas',estado:'Estado del sistema',camaras:'Cámaras activas',ayuda:'Ayuda del panel',rol:'Mi rol y permisos'};
  const input=document.getElementById('hermes-input');
  if(input)input.value=labels[key]||key;
  await window.hermesEnviar();
};
