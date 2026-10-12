// MessageBubble — renderiza un mensaje del chat condicionalmente
// según tipo, severidad, fuentes, etapas, tiempos y herramientas usadas

import { useState } from 'react'
import type { ChatMessage } from '../types/hermes'
import { QuickActions } from './QuickActions'
import { BotIcon, UserIcon, PinIcon, AlertTriangleIcon, ClockIcon } from './Icons'

interface Props {
  message:       ChatMessage
  onSuggestion:  (text: string) => void
}

/** Sanitiza texto para prevenir XSS */
function safe(text: string): string {
  return text.replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function MessageBubble({ message, onSuggestion }: Props) {
  const { from, contenido, timestamp, response } = message
  const isUser = from === 'user'
  const tipo   = response?.tipo ?? 'info'
  const [showDetails, setShowDetails] = useState(false)

  // Clases CSS condicionales por tipo
  const bubbleClass = isUser
    ? 'h-bubble user'
    : `h-bubble hermes ${tipo === 'denegado' || tipo === 'error' ? tipo : tipo === 'alerta' ? 'alerta' : ''}`

  const totalMs = response?.tiempos_ms?.total_ms

  return (
    <div className={`h-bubble-row ${from}`} data-intent={response?.intencion_detectada}>

      {/* Avatar */}
      {!isUser && (
        <div className="h-bubble-avatar hermes" aria-hidden>
          <BotIcon width={16} height={16} />
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', flex: 1, minWidth: 0 }}>
        {/* Burbuja principal */}
        <div
          className={bubbleClass}
          dangerouslySetInnerHTML={{ __html: formatContent(safe(contenido)) }}
        />

        {/* Metadatos inferiores: hora + modo + modelo + latencia */}
        <div className={`h-bubble-meta ${isUser ? 'user' : ''}`}>
          <span className="h-bubble-time">{timestamp}</span>

          {response?.modo && !isUser && (
            <span className="h-intent-tag h-modo-tag">
              {response.modo}
            </span>
          )}

          {response?.modelo && !isUser && (
            <span className="h-intent-tag h-model-tag">
              {response.modelo}
            </span>
          )}

          {typeof totalMs === 'number' && !isUser && (
            <button
              type="button"
              className="h-perf-toggle"
              onClick={() => setShowDetails(!showDetails)}
              title="Ver tiempos y etapas de procesamiento"
            >
              <ClockIcon width={10} height={10} style={{ marginRight: 2 }} />
              {totalMs} ms
            </button>
          )}
        </div>

        {/* Detalle expandible de rendimiento / observabilidad */}
        {!isUser && showDetails && response && (
          <div className="h-perf-details">
            <div className="h-perf-title">Diagnóstico de procesamiento:</div>
            {response.etapas_procesamiento && response.etapas_procesamiento.length > 0 && (
              <div className="h-perf-stages">
                <strong>Etapas:</strong> {response.etapas_procesamiento.join(' → ')}
              </div>
            )}
            {response.tiempos_ms && Object.keys(response.tiempos_ms).length > 0 && (
              <div className="h-perf-times">
                {Object.entries(response.tiempos_ms).map(([k, v]) => (
                  <span key={k} className="h-perf-pill">{k.replace('_ms', '')}: {v}ms</span>
                ))}
              </div>
            )}
            {response.herramientas_usadas && response.herramientas_usadas.length > 0 && (
              <div className="h-perf-tools">
                <strong>Herramientas:</strong> {response.herramientas_usadas.join(', ')}
              </div>
            )}
          </div>
        )}

        {/* Advertencias */}
        {!isUser && response?.advertencias && response.advertencias.length > 0 && (
          <div className="h-warning-banner">
            <AlertTriangleIcon width={12} height={12} style={{ marginRight: 4, flexShrink: 0 }} />
            <span>{response.advertencias.join(' · ')}</span>
          </div>
        )}

        {/* Fuentes verificadas */}
        {!isUser && response?.fuentes && response.fuentes.length > 0 && (
          <div className="h-sources-row">
            {response.fuentes.map((f, i) => (
              <span key={i} className="h-source-chip" title={f.referencia}>
                <PinIcon width={10} height={10} style={{ marginRight: 3, verticalAlign: 'middle' }} />
                {f.titulo || f.referencia}
              </span>
            ))}
          </div>
        )}

        {/* Alert chips */}
        {!isUser && response?.alertas_resumen && response.alertas_resumen.length > 0 && (
          <div className="h-alert-chips">
            {response.alertas_resumen.slice(0, 4).map((a, i) => (
              <div key={i} className="h-alert-chip">
                <span className="chip-hora">{a.hora}</span>
                <span>{a.camara_codigo}</span>
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

      {isUser && (
        <div className="h-bubble-avatar user" aria-hidden>
          <UserIcon width={16} height={16} />
        </div>
      )}
    </div>
  )
}

/**
 * Convierte el texto markdown-básico en HTML seguro.
 */
function formatContent(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code class="h-inline-code">$1</code>')
    .replace(/\n/g, '<br/>')
}
