// HermesChat — componente raíz del panel de chat
// Orquesta el historial, input, typing indicator y status bar con controles de panel lateral y flotante

import { useRef, useEffect, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useHermesStore } from '../store/useHermesStore'
import { useChat }        from '../hooks/useChat'
import { MessageBubble }  from './MessageBubble'
import { TypingIndicator } from './TypingIndicator'
import { SystemStatusCard } from './SystemStatusCard'
import {
  BotIcon, TrashIcon, CloseIcon, MinimizeIcon,
  MaximizeIcon, LayoutSidebarIcon, LayoutFloatIcon
} from './Icons'

interface Props {
  apiBase:    string
  token:      string
  onClose:    () => void
  isFloating: boolean
  isMinimized: boolean
  onToggleLayout: () => void
  onToggleMinimize: () => void
}

const STARTERS = [
  '¿Cuál es el estado de CPU, RAM y disco?',
  '¿Cuántas cámaras existen?',
  '¿Existe una cámara llamada Chavi?',
  '¿Qué detectó el último evento?',
  '¿Cuántas alertas hay hoy?',
]

export function HermesChat({
  apiBase, token, onClose, isFloating, isMinimized,
  onToggleLayout, onToggleMinimize
}: Props) {
  const { messages, isLoading, systemHealth, clearMessages } = useHermesStore()
  const { sendMessage } = useChat()
  const [input, setInput] = useState('')
  const [lastQuery, setLastQuery] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll al fondo al llegar nuevo mensaje
  useEffect(() => {
    if (!isMinimized) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isLoading, isMinimized])

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
    setLastQuery(msg)
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
    setLastQuery(text)
    sendMessage({ mensaje: text, apiBase, token })
  }

  const isEmpty = messages.length === 0

  return (
    <>
      {/* Header — Sobrio con controles de modo de visualización */}
      <div className="h-header" data-drag-handle="true">
        <div className="h-header-avatar" aria-hidden>
          <BotIcon width={18} height={18} />
        </div>
        <div className="h-header-info">
          <h3>Hermes IA</h3>
          <span>Asistente Operativo ARGOS · {isFloating ? 'Ventana flotante' : 'Panel lateral'}</span>
        </div>
        <div className="h-status-dot" title="Sistema conectado" />
        <div className="h-header-actions">
          <button
            id="hermes-layout-btn"
            className="h-icon-btn"
            onClick={onToggleLayout}
            title={isFloating ? 'Cambiar a panel lateral' : 'Cambiar a ventana flotante'}
            aria-label={isFloating ? 'Cambiar a panel lateral' : 'Cambiar a ventana flotante'}
          >
            {isFloating ? <LayoutSidebarIcon width={14} height={14} /> : <LayoutFloatIcon width={14} height={14} />}
          </button>
          <button
            id="hermes-minimize-btn"
            className="h-icon-btn"
            onClick={onToggleMinimize}
            title={isMinimized ? 'Expandir' : 'Minimizar'}
            aria-label={isMinimized ? 'Expandir' : 'Minimizar'}
          >
            {isMinimized ? <MaximizeIcon width={14} height={14} /> : <MinimizeIcon width={14} height={14} />}
          </button>
          <button
            id="hermes-clear-btn"
            className="h-icon-btn"
            onClick={clearMessages}
            title="Limpiar conversación"
            aria-label="Limpiar conversación"
          >
            <TrashIcon width={14} height={14} />
          </button>
          <button
            id="hermes-close-btn"
            className="h-icon-btn"
            onClick={onClose}
            title="Cerrar Hermes"
            aria-label="Cerrar panel de Hermes"
          >
            <CloseIcon width={14} height={14} />
          </button>
        </div>
      </div>

      {/* Si está minimizado, solo mostramos el header compacto */}
      {!isMinimized && (
        <>
          {/* System status bar */}
          {systemHealth && <SystemStatusCard snapshot={systemHealth} />}

          {/* Messages / Welcome */}
          <div className="h-messages" role="log" aria-live="polite" aria-label="Conversación con Hermes">
            {isEmpty ? (
              <div className="h-welcome">
                <div className="h-welcome-icon">
                  <BotIcon width={28} height={28} />
                </div>
                <h4>Hermes IA</h4>
                <p>
                  Asistente inteligente y analítico de ARGOS SiViA.<br />
                  Consultas factuales de cámaras, eventos, infraestructura y conocimiento técnico local.
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
                {isLoading && <TypingIndicator query={lastQuery} />}
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
                placeholder="Escribe tu consulta operativa…"
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
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            </div>
            <p className="h-input-hint">
              Enter para enviar · Shift+Enter para nueva línea
            </p>
          </div>
        </>
      )}
    </>
  )
}
