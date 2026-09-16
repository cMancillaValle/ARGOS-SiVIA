// MessageBubble — renderiza un mensaje del chat condicionalmente
// según tipo, severidad, alertas_resumen, acciones y sugerencias

import type { ChatMessage } from '../types/hermes'
import { QuickActions } from './QuickActions'

interface Props {
  message:       ChatMessage
  onSuggestion:  (text: string) => void
}

/** Sanitiza texto para prevenir XSS al insertarlo como innerText */
function safe(text: string): string {
  return text.replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function MessageBubble({ message, onSuggestion }: Props) {
  const { from, contenido, timestamp, response } = message
  const isUser = from === 'user'
  const tipo   = response?.tipo ?? 'info'

  // Clases CSS condicionales por tipo
  const bubbleClass = isUser
    ? 'h-bubble user'
    : `h-bubble hermes ${tipo === 'denegado' || tipo === 'error' ? tipo : tipo === 'alerta' ? 'alerta' : ''}`

  return (
    <div className={`h-bubble-row ${from}`} data-intent={response?.intencion_detectada}>

      {/* Avatar */}
      {!isUser && <div className="h-bubble-avatar hermes" aria-hidden>🤖</div>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', flex: 1 }}>
        {/* Burbuja principal */}
        <div
          className={bubbleClass}
          dangerouslySetInnerHTML={{ __html: formatContent(safe(contenido)) }}
        />

        {/* Meta: hora + intent tag */}
        <div className={`h-bubble-meta ${isUser ? 'user' : ''}`}
             style={{ justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
          <span className="h-bubble-time">{timestamp}</span>
          {response?.intencion_detectada && response.intencion_detectada !== 'desconocido' && !isUser && (
            <span className="h-intent-tag">{response.intencion_detectada.replace('_', ' ')}</span>
          )}
        </div>

        {/* Alert chips — solo en mensajes de hermes con alertas */}
        {!isUser && response?.alertas_resumen && response.alertas_resumen.length > 0 && (
          <div className="h-alert-chips">
            {response.alertas_resumen.slice(0, 4).map((a, i) => (
              <div key={i} className="h-alert-chip">
                <span className="chip-hora">{a.hora}</span>
                <span>📷 {a.camara_codigo}</span>
                <span style={{ color: 'var(--h-text-muted)' }}>{a.estacion}</span>
                <span className="chip-conf">{a.confianza_pct}%</span>
              </div>
            ))}
          </div>
        )}

        {/* Acciones rápidas */}
        {!isUser && response?.acciones && response.acciones.length > 0 && (
          <QuickActions acciones={response.acciones} />
        )}

        {/* Sugerencias de seguimiento */}
        {!isUser && response?.sugerencias && response.sugerencias.length > 0 && (
          <div className="h-suggestions">
            {response.sugerencias.map((s, i) => (
              <button
                key={i}
                id={`hermes-sugg-${message.id}-${i}`}
                className="h-suggestion-pill"
                onClick={() => onSuggestion(s)}
                title={s}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {isUser && <div className="h-bubble-avatar user" aria-hidden>👤</div>}
    </div>
  )
}

/**
 * Convierte el texto markdown-básico en HTML seguro.
 * Solo soporta **bold** y saltos de línea.
 * El contenido ya viene escapado por safe().
 */
function formatContent(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code style="background:rgba(99,102,241,0.15);padding:1px 5px;border-radius:4px;font-size:12px">$1</code>')
    .replace(/\n/g, '<br/>')
}
