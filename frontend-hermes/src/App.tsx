// App.tsx — Root del widget React
// Inicializa como panel lateral derecho y permite alternar a ventana flotante arrastrable
// con persistencia de preferencias y coordenadas en localStorage

import { useState, useEffect, useRef } from 'react'
import { HermesChat } from './components/HermesChat'
import { useHermesStore } from './store/useHermesStore'

interface AppProps {
  apiBase: string
  token:   string
  modulo:  string
}

interface Posicion {
  x: number
  y: number
}

const STORAGE_LAYOUT_KEY = 'argos_hermes_layout_mode' // 'sidebar' | 'floating'
const STORAGE_POS_KEY    = 'argos_hermes_pos'

export function App({ apiBase, token, modulo }: AppProps) {
  const [open, setOpen] = useState(false)
  const [closing, setClosing] = useState(false)
  const [layoutMode, setLayoutMode] = useState<'sidebar' | 'floating'>(() => {
    return (localStorage.getItem(STORAGE_LAYOUT_KEY) as 'sidebar' | 'floating') || 'sidebar'
  })
  const [isMinimized, setIsMinimized] = useState(false)
  const [pos, setPos] = useState<Posicion>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_POS_KEY)
      if (saved) return JSON.parse(saved)
    } catch {
      // Ignorar fallback
    }
    return { x: window.innerWidth - 440, y: 100 }
  })

  const { setModule } = useHermesStore()
  const isDraggingRef = useRef(false)
  const dragOffsetRef = useRef({ x: 0, y: 0 })

  // Sincronizar módulo del dashboard al widget
  useEffect(() => {
    if (modulo) setModule(modulo)
  }, [modulo, setModule])

  // Escuchar evento global desde el topbar para abrir/cerrar
  useEffect(() => {
    const handleToggle = () => setOpen(old => {
      if (old) { handleClose(); return old }
      return true
    })
    const handleCloseEvent = () => setOpen(old => {
      if (old) { handleClose() }
      return old
    })

    window.addEventListener('toggle-hermes', handleToggle)
    window.addEventListener('close-hermes', handleCloseEvent)

    return () => {
      window.removeEventListener('toggle-hermes', handleToggle)
      window.removeEventListener('close-hermes', handleCloseEvent)
    }
  }, [])

  const handleClose = () => {
    setClosing(true)
    setTimeout(() => {
      setOpen(false)
      setClosing(false)
    }, 180)
  }

  const handleToggleLayout = () => {
    const next = layoutMode === 'sidebar' ? 'floating' : 'sidebar'
    setLayoutMode(next)
    localStorage.setItem(STORAGE_LAYOUT_KEY, next)
    if (next === 'floating') {
      // Reposicionar dentro de la ventana de forma segura
      const safeX = Math.max(20, Math.min(window.innerWidth - 420, pos.x))
      const safeY = Math.max(20, Math.min(window.innerHeight - 500, pos.y))
      setPos({ x: safeX, y: safeY })
    }
  }

  const handleToggleMinimize = () => {
    setIsMinimized(prev => !prev)
  }

  // Lógica de arrastre para ventana flotante
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (layoutMode !== 'floating') return
    const target = e.target as HTMLElement
    // Solo arrastrar si se agarra del header o de un elemento con data-drag-handle
    if (!target.closest('[data-drag-handle="true"]')) return
    // No iniciar arrastre si se hizo clic en un botón de acción
    if (target.closest('button')) return

    isDraggingRef.current = true
    dragOffsetRef.current = {
      x: e.clientX - pos.x,
      y: e.clientY - pos.y
    }

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return
      const panelWidth = 400
      const panelHeight = isMinimized ? 60 : 600
      const newX = Math.max(10, Math.min(window.innerWidth - panelWidth - 10, moveEvent.clientX - dragOffsetRef.current.x))
      const newY = Math.max(10, Math.min(window.innerHeight - panelHeight - 10, moveEvent.clientY - dragOffsetRef.current.y))

      setPos({ x: newX, y: newY })
    }

    const handleMouseUp = () => {
      isDraggingRef.current = false
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      setPos(current => {
        try {
          localStorage.setItem(STORAGE_POS_KEY, JSON.stringify(current))
        } catch {
          // ignore
        }
        return current
      })
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  const panelStyles: React.CSSProperties = layoutMode === 'floating'
    ? {
        position: 'fixed',
        left: `${pos.x}px`,
        top: `${pos.y}px`,
        right: 'auto',
        bottom: 'auto',
        margin: 0,
        height: isMinimized ? '54px' : '620px',
        maxHeight: 'calc(100vh - 40px)',
        zIndex: 9999,
        cursor: isDraggingRef.current ? 'grabbing' : 'default'
      }
    : {
        height: isMinimized ? '54px' : undefined
      }

  return (
    <>
      {open && (
        <div
          className={`hermes-panel ${layoutMode === 'sidebar' ? 'hermes-sidebar-mode' : 'hermes-floating-mode'} ${isMinimized ? 'is-minimized' : ''} ${closing ? 'closing' : ''}`}
          style={panelStyles}
          onMouseDown={handleMouseDown}
          role="dialog"
          aria-label="Hermes IA — Asistente ARGOS"
          aria-modal="false"
        >
          <HermesChat
            apiBase={apiBase}
            token={token}
            onClose={handleClose}
            isFloating={layoutMode === 'floating'}
            isMinimized={isMinimized}
            onToggleLayout={handleToggleLayout}
            onToggleMinimize={handleToggleMinimize}
          />
        </div>
      )}
    </>
  )
}
