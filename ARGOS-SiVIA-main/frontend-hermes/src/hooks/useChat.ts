// Hermes IA — useChat hook
// Gestión del estado asíncrono del chat: envío de mensajes y fetch

import { useCallback } from 'react'
import type { HermesResponse, ChatMessage } from '../types/hermes'
import { useHermesStore } from '../store/useHermesStore'

interface SendOptions {
  mensaje:        string
  apiBase:        string
  token:          string
}

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function useChat() {
  const {
    addMessage, setLoading, setSystemHealth,
    currentModule, activeFilters, sessionId,
  } = useHermesStore()

  const sendMessage = useCallback(async ({ mensaje, apiBase, token }: SendOptions) => {
    if (!mensaje.trim()) return

    // 1. Añadir mensaje del usuario al historial
    const userMsg: ChatMessage = {
      id:        uid(),
      from:      'user',
      contenido: mensaje,
      timestamp: new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }),
    }
    addMessage(userMsg)
    setLoading(true)

    try {
      const res = await fetch(`${apiBase}/chat`, {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Token':      token,
        },
        body: JSON.stringify({
          mensaje,
          modulo:          currentModule,
          filtros_activos: activeFilters,
          session_id:      sessionId,
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData?.error || `HTTP ${res.status}`)
      }

      const data: HermesResponse = await res.json()

      // 2. Actualizar snapshot de salud del sistema
      if (data.estado_sistema) {
        setSystemHealth(data.estado_sistema)
      }

      // 3. Añadir respuesta de Hermes al historial
      const botMsg: ChatMessage = {
        id:        uid(),
        from:      'hermes',
        contenido: data.contenido,
        timestamp: new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }),
        response:  data,
      }
      addMessage(botMsg)

    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : 'Error de conexión'
      const errorBotMsg: ChatMessage = {
        id:        uid(),
        from:      'hermes',
        contenido: `❌ Error: ${errMsg}. Verifica tu conexión e inténtalo de nuevo.`,
        timestamp: new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }),
        response: {
          tipo: 'error', severidad: 'critical', contenido: errMsg,
          alertas_resumen: [], acciones: [], sugerencias: [],
          estado_sistema: null, intencion_detectada: 'error',
          rol_usuario: '', timestamp: '', session_id: null,
        },
      }
      addMessage(errorBotMsg)
    } finally {
      setLoading(false)
    }
  }, [addMessage, setLoading, setSystemHealth, currentModule, activeFilters, sessionId])

  return { sendMessage }
}
