// Hermes IA Widget — TypeScript Types
// Espejo exacto del contrato Pydantic del backend

export type AlertaSeveridad = 'normal' | 'warning' | 'critical'
export type MensajeTipo = 'info' | 'alerta' | 'error' | 'confirmacion' | 'denegado' | 'ayuda' | 'desconocido'

export interface AlertaSummary {
  camara_codigo:  string
  estacion:       string
  tipo:           string
  hora:           string
  confianza_pct:  number
}

export interface AccionSugerida {
  id:                  string
  label:               string
  endpoint?:           string
  metodo:              'GET' | 'POST' | 'PUT' | 'DELETE'
  payload?:            Record<string, unknown>
  permiso_requerido?:  string
}

export interface SystemHealthSnapshot {
  nivel:              AlertaSeveridad
  camaras_total:      number
  camaras_activas:    number
  camaras_offline:    number
  alertas_pendientes: number
  fps_estimado:       number
  uptime_pct:         number
  evaluado_en:        string
}

/** Contrato de respuesta del backend /api/chat */
export interface HermesResponse {
  tipo:                MensajeTipo
  severidad:           AlertaSeveridad
  contenido:           string
  alertas_resumen:     AlertaSummary[]
  acciones:            AccionSugerida[]
  sugerencias:         string[]
  estado_sistema:      SystemHealthSnapshot | null
  intencion_detectada: string
  rol_usuario:         string
  timestamp:           string
  session_id:          string | null
}

/** Mensaje individual en el historial del chat */
export interface ChatMessage {
  id:        string
  from:      'user' | 'hermes'
  contenido: string
  timestamp: string
  response?: HermesResponse   // solo para mensajes de hermes
}
