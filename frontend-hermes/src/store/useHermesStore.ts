// Hermes IA — Zustand Store
// Estado global del widget: mensajes, sesión, salud del sistema

import { create } from 'zustand'
import type { ChatMessage, SystemHealthSnapshot } from '../types/hermes'

interface HermesState {
  // Chat
  messages:       ChatMessage[]
  isLoading:      boolean
  // Contexto del widget
  currentModule:  string
  activeFilters:  Record<string, string>
  // Salud del sistema (última captura)
  systemHealth:   SystemHealthSnapshot | null
  // Sesión
  sessionId:      string
  // Acciones
  addMessage:     (msg: ChatMessage) => void
  setLoading:     (v: boolean) => void
  setModule:      (m: string) => void
  setFilters:     (f: Record<string, string>) => void
  setSystemHealth:(s: SystemHealthSnapshot | null) => void
  clearMessages:  () => void
}

function generateSessionId(): string {
  return `hs_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
}

export const useHermesStore = create<HermesState>((set) => ({
  messages:      [],
  isLoading:     false,
  currentModule: 'dashboard',
  activeFilters: {},
  systemHealth:  null,
  sessionId:     generateSessionId(),

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  setLoading: (v) => set({ isLoading: v }),

  setModule: (m) => set({ currentModule: m }),

  setFilters: (f) => set({ activeFilters: f }),

  setSystemHealth: (s) => set({ systemHealth: s }),

  clearMessages: () => set({ messages: [], sessionId: generateSessionId() }),
}))
