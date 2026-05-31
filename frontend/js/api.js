/**
 * ARGOS - SiViA · API Client
 * ──────────────────────────
 * Capa de comunicación entre el frontend y el backend Flask.
 * Incluye: autenticación, cámaras, eventos, estadísticas y Hermes IA.
 */

// Auto-detect backend URL
// · Localhost/LAN  → usa el host actual (funciona con Ngrok automáticamente)
// · Ngrok / dominio externo → usa window.location.origin
const API_BASE = (function() {
  const origin = window.location.origin;
  // Si viene de ngrok.io / ngrok-free.app o cualquier dominio externo, usa ese mismo origen
  return origin + '/api';
})();

// ══════════════════════════════════════════════════════
//  SESIÓN
// ══════════════════════════════════════════════════════

const Session = {
  getToken:   () => sessionStorage.getItem('argos_token'),
  getUser:    () => { try { return JSON.parse(sessionStorage.getItem('argos_user')); } catch { return null; } },
  setSession: (token, user) => {
    sessionStorage.setItem('argos_token', token);
    sessionStorage.setItem('argos_user', JSON.stringify(user));
  },
  clear: () => {
    sessionStorage.removeItem('argos_token');
    sessionStorage.removeItem('argos_user');
  },
  isLoggedIn: () => !!sessionStorage.getItem('argos_token'),
};


// ══════════════════════════════════════════════════════
//  HTTP BASE
// ══════════════════════════════════════════════════════

async function apiFetch(endpoint, options = {}) {
  const token = Session.getToken();
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-Token': token } : {}),
      ...(options.headers || {}),
    },
    ...options,
  };
  if (config.body && typeof config.body !== 'string') {
    config.body = JSON.stringify(config.body);
  }

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, config);
    const data = await res.json();
    if (res.status === 401) {
      Session.clear();
      window.location.href = 'login.html';
      return null;
    }
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    console.error('[ARGOS API] Error de red:', err);
    return { ok: false, status: 0, data: { error: 'No se pudo conectar al servidor.' } };
  }
}


// ══════════════════════════════════════════════════════
//  AUTH
// ══════════════════════════════════════════════════════

const Auth = {
  async login(usuario, password, rol) {
    const res = await apiFetch('/auth/login', {
      method: 'POST',
      body: { usuario, password, rol },
    });
    if (res?.ok) {
      Session.setSession(res.data.token, res.data.usuario);
    }
    return res;
  },

  async logout() {
    await apiFetch('/auth/logout', { method: 'POST' });
    Session.clear();
    // Caller handles redirect
  },

  async me() {
    const res = await apiFetch('/auth/me');
    return res?.data?.usuario || null;
  },
};


// ══════════════════════════════════════════════════════
//  CÁMARAS
// ══════════════════════════════════════════════════════

const Camaras = {
  async listar(filtros = {}) {
    const params = new URLSearchParams(filtros).toString();
    const res = await apiFetch(`/camaras${params ? '?' + params : ''}`);
    return res?.data || { camaras: [], total: 0 };
  },

  async stats() {
    const res = await apiFetch('/camaras/stats');
    return res?.data || {};
  },

  async obtener(id) {
    const res = await apiFetch(`/camaras/${id}`);
    return res?.data || null;
  },

  async crear(datos) {
    return await apiFetch('/camaras', { method: 'POST', body: datos });
  },

  async actualizar(id, datos) {
    return await apiFetch(`/camaras/${id}`, { method: 'PUT', body: datos });
  },

  async eliminar(id) {
    return await apiFetch(`/camaras/${id}`, { method: 'DELETE' });
  },
};


// ══════════════════════════════════════════════════════
//  EVENTOS
// ══════════════════════════════════════════════════════

const Eventos = {
  async listar(filtros = {}) {
    const params = new URLSearchParams(filtros).toString();
    const res = await apiFetch(`/eventos${params ? '?' + params : ''}`);
    return res?.data || { eventos: [], total: 0 };
  },

  async pendientes() {
    const res = await apiFetch('/eventos/pendientes');
    return res?.data || { eventos: [], total: 0 };
  },

  async obtener(id) {
    const res = await apiFetch(`/eventos/${id}`);
    return res?.data || null;
  },

  async registrar(datos) {
    return await apiFetch('/eventos', { method: 'POST', body: datos });
  },

  async actualizarEstado(id, estado, observaciones = '') {
    return await apiFetch(`/eventos/${id}/estado`, {
      method: 'PUT',
      body: { estado, observaciones },
    });
  },
};


// ══════════════════════════════════════════════════════
//  ESTADÍSTICAS
// ══════════════════════════════════════════════════════

const Stats = {
  async general() {
    const res = await apiFetch('/stats');
    return res?.data || {};
  },

  async hoy() {
    const res = await apiFetch('/stats/hoy');
    return res?.data || {};
  },

  async auditoria(limite = 100) {
    const res = await apiFetch(`/stats/auditoria?limite=${limite}`);
    return res?.data || { registros: [] };
  },
};


// ══════════════════════════════════════════════════════
//  USUARIOS
// ══════════════════════════════════════════════════════

const Usuarios = {
  async listar() {
    const res = await apiFetch('/usuarios');
    return res?.data || { usuarios: [], total: 0 };
  },

  async obtener(id) {
    const res = await apiFetch(`/usuarios/${id}`);
    return res?.data || null;
  },

  async crear(datos) {
    return await apiFetch('/usuarios', { method: 'POST', body: datos });
  },

  async actualizar(id, datos) {
    return await apiFetch(`/usuarios/${id}`, { method: 'PUT', body: datos });
  },

  async desactivar(id) {
    return await apiFetch(`/usuarios/${id}`, { method: 'DELETE' });
  },

  async cambiarPassword(id, nuevaPassword) {
    return await apiFetch(`/usuarios/${id}/password`, {
      method: 'PUT',
      body: { nueva_password: nuevaPassword },
    });
  },
};


// ══════════════════════════════════════════════════════
//  HERMES IA
// ══════════════════════════════════════════════════════

const Hermes = {
  async enviar(mensaje) {
    const res = await apiFetch('/chat', {
      method: 'POST',
      body: { mensaje },
    });
    return res?.data?.respuesta || 'No pude obtener respuesta del servidor.';
  },
};


// ══════════════════════════════════════════════════════
//  UTILIDADES UI
// ══════════════════════════════════════════════════════

const UI = {
  /**
   * Muestra una notificación toast en pantalla.
   * tipo: 'success' | 'error' | 'warning' | 'info'
   */
  toast(mensaje, tipo = 'info', duracion = 3500) {
    const colors = {
      success: 'var(--verde)',
      error:   'var(--rojo)',
      warning: 'var(--amarillo)',
      info:    'var(--azul)',
    };
    const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
    const toast = document.createElement('div');
    toast.style.cssText = `
      position: fixed; bottom: 90px; right: 24px; z-index: 9999;
      background: var(--bg2); border: 1px solid ${colors[tipo]};
      color: var(--texto); font-family: 'Exo 2', sans-serif;
      font-size: 13px; padding: 12px 18px; border-radius: 8px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
      display: flex; align-items: center; gap: 10px;
      animation: fadeUp 0.3s ease; max-width: 360px;
    `;
    toast.innerHTML = `<span style="color:${colors[tipo]};font-size:15px">${icons[tipo]}</span>${mensaje}`;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(() => toast.remove(), 320);
    }, duracion);
  },

  /** Formatea fecha ISO a formato legible en español */
  formatFecha(isoStr) {
    if (!isoStr) return '-';
    return new Date(isoStr).toLocaleString('es-CO', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  },

  /** Badge de confianza coloreado */
  badgeConfianza(valor) {
    const pct  = Math.round(valor * 100);
    const color = pct >= 90 ? 'var(--rojo)' : pct >= 75 ? 'var(--amarillo)' : 'var(--verde)';
    return `<span style="color:${color};font-family:'Share Tech Mono',monospace;font-size:11px">${pct}%</span>`;
  },

  /** Badge de estado de evento */
  badgeEstado(estado) {
    const map = {
      pendiente:  { color: 'var(--amarillo)', bg: 'rgba(255,200,0,0.1)' },
      confirmado: { color: 'var(--rojo)',     bg: 'rgba(232,0,29,0.1)' },
      descartado: { color: 'var(--texto-dim)',bg: 'rgba(122,147,178,0.1)' },
    };
    const s = map[estado] || map.pendiente;
    return `<span style="color:${s.color};background:${s.bg};padding:2px 8px;border-radius:3px;font-size:10px;font-family:'Share Tech Mono',monospace;letter-spacing:1px;text-transform:uppercase">${estado}</span>`;
  },

  /** Badge de estado de cámara */
  badgeCamara(estado) {
    const map = {
      activa:        { color: 'var(--verde)',   icon: '●' },
      offline:       { color: 'var(--rojo)',    icon: '●' },
      mantenimiento: { color: 'var(--amarillo)',icon: '●' },
    };
    const s = map[estado] || { color: 'var(--texto-dim)', icon: '●' };
    return `<span style="color:${s.color}">${s.icon}</span> ${estado}`;
  },
};




// ══════════════════════════════════════════════════════
//  AUDITORÍA
// ══════════════════════════════════════════════════════

const Auditoria = {
  async listar(filtros = {}) {
    const params = new URLSearchParams(filtros).toString();
    const res = await apiFetch(`/auditoria${params ? '?' + params : ''}`);
    return res?.data || { registros: [], total: 0, usuarios: [] };
  },

  async stats() {
    const res = await apiFetch('/auditoria/stats');
    return res?.data || {};
  },

  async chart() {
    const res = await apiFetch('/auditoria/chart');
    return res?.data || { chart: [] };
  },

  async exportCSV(filtros = {}) {
    const params = new URLSearchParams(filtros).toString();
    const url = `${API_BASE}/auditoria/export${params ? '?' + params : ''}`;
    
    // Fetch manual para usar Headers y evitar Token en Query
    const token = Session.getToken();
    const headers = { ...(token ? { 'X-Token': token } : {}) };
    
    try {
      const res = await fetch(url, { headers });
      if (!res.ok) {
        throw new Error('Error al generar la exportación');
      }
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(blob);
      a.download = `auditoria_export_${new Date().toISOString().slice(0,10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (err) {
      console.error(err);
      UI.toast('No se pudo generar la exportación CSV', 'error');
    }
  },
};

// ══════════════════════════════════════════════════════
//  EXPORTAR (disponible globalmente)
// ══════════════════════════════════════════════════════

window.ARGOS = { Session, Auth, Camaras, Eventos, Stats, Usuarios, Auditoria, Hermes, UI };

// Función global para mostrar/ocultar contraseñas
window.togglePasswordVisibility = function(button, inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isPassword = input.type === 'password';
  input.type = isPassword ? 'text' : 'password';
  if (isPassword) {
    button.innerHTML = `<svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a9.978 9.978 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.542 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>`;
  } else {
    button.innerHTML = `<svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>`;
  }
};
