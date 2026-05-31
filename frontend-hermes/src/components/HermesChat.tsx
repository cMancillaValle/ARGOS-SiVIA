// HermesChat — componente raíz del panel de chat
// Orquesta el historial, input, typing indicator y status bar

import { useRef, useEffect, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useHermesStore } from '../store/useHermesStore'
import { useChat }        from '../hooks/useChat'
import { MessageBubble }  from './MessageBubble'
import { TypingIndicator } from './TypingIndicator'
import { SystemStatusCard } from './SystemStatusCard'

interface Props {
  apiBase: string
  token:   string
  onClose: () => void
}

const STARTERS = [
  '¿Cuál es el estado del sistema?',
  '¿Cuántas cámaras están offline?',
  '¿Cuántas alertas hay hoy?',
  '¿Cuál es mi rol?',
]

export function HermesChat({ apiBase, token, onClose }: Props) {
  const { messages, isLoading, systemHealth, clearMessages } = useHermesStore()
  const { sendMessage } = useChat()
  const [input, setInput]   = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll al fondo al llegar nuevo mensaje
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 100)}px`
  }, [input])

  const handleSend = () => {
    const msg = input.trim()
    if (!msg || isLoading) return
    setInput('')
    sendMessage({ mensaje: msg, apiBase, token })
  }

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSuggestion = (text: string) => {
    sendMessage({ mensaje: text, apiBase, token })
  }

  const isEmpty = messages.length === 0

  return (
    <>
      {/* Header */}
      <div className="h-header">
        <div className="h-header-avatar" aria-hidden>🤖</div>
        <div className="h-header-info">
          <h3>Hermes IA</h3>
          <span>Asistente ARGOS · Activo</span>
        </div>
        <div className="h-status-dot" title="Sistema conectado" />
        <div className="h-header-actions">
          <button
            id="hermes-clear-btn"
            className="h-icon-btn"
            onClick={clearMessages}
            title="Limpiar conversación"
            aria-label="Limpiar conversación"
          >
            🗑
          </button>
          <button
            id="hermes-close-btn"
            className="h-icon-btn"
            onClick={onClose}
            title="Cerrar Hermes"
            aria-label="Cerrar panel de Hermes"
          >
            ✕
          </button>
        </div>
      </div>

      {/* System status bar */}
      {systemHealth && <SystemStatusCard snapshot={systemHealth} />}

      {/* Messages / Welcome */}
      <div className="h-messages" role="log" aria-live="polite" aria-label="Conversación con Hermes">
        {isEmpty ? (
          <div className="h-welcome">
            <div className="h-welcome-icon">🤖</div>
            <h4>Hola, soy Hermes</h4>
            <p>
              Tu asistente inteligente de ARGOS SiViA.<br/>
              Puedo informarte sobre el estado del sistema, cámaras, alertas y más.
            </p>
            <div className="h-quick-starters">
              {STARTERS.map((s, i) => (
                <button
                  key={i}
                  id={`hermes-starter-${i}`}
                  className="h-starter-pill"
                  onClick={() => handleSuggestion(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                onSuggestion={handleSuggestion}
              />
            ))}
            {isLoading && <TypingIndicator />}
          </>
        )}
        <div ref={bottomRef} aria-hidden />
      </div>

      {/* Input area */}
      <div className="h-input-area">
        <div className="h-input-row">
          <textarea
            ref={textareaRef}
            id="hermes-input"
            className="h-input"
            placeholder="Escribe tu consulta…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            disabled={isLoading}
            rows={1}
            aria-label="Mensaje para Hermes"
          />
          <button
            id="hermes-send-btn"
            className="h-send-btn"
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            aria-label="Enviar mensaje"
          >
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
          </button>
        </div>
        <p className="h-input-hint">
          Enter para enviar · Shift+Enter para nueva línea<br/>
          En construcción hasta: V2.0
        </p>
      </div>
    </>
  )
}
