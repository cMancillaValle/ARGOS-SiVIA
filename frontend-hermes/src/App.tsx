// App.tsx — Root del widget React
// Gestiona el FAB (botón flotante) y el panel del chat

import { useState, useEffect } from 'react'
import { HermesChat } from './components/HermesChat'
import { useHermesStore } from './store/useHermesStore'

interface AppProps {
  apiBase: string
  token:   string
  modulo:  string
}

export function App({ apiBase, token, modulo }: AppProps) {
  const [open, setOpen] = useState(false)
  const [closing, setClosing] = useState(false)
  const { setModule } = useHermesStore()

  // Sincronizar módulo del dashboard al widget
  useEffect(() => {
    if (modulo) setModule(modulo)
  }, [modulo, setModule])

  // Escuchar evento global desde el topbar para abrir/cerrar
  useEffect(() => {
    const handleToggle = () => setOpen(old => {
      if (old) { handleClose(); return old; }
      return true;
    });
    const handleCloseEvent = () => setOpen(old => {
      if (old) { handleClose(); }
      return old;
    });
    
    window.addEventListener('toggle-hermes', handleToggle);
    window.addEventListener('close-hermes', handleCloseEvent);
    
    return () => {
      window.removeEventListener('toggle-hermes', handleToggle);
      window.removeEventListener('close-hermes', handleCloseEvent);
    };
  }, []);



  const handleClose = () => {
    setClosing(true)
    setTimeout(() => {
      setOpen(false)
      setClosing(false)
    }, 180)
  }

  return (
    <>
      {/* Panel */}
      {open && (
        <div className={`hermes-panel ${closing ? 'closing' : ''}`}
             role="dialog"
             aria-label="Hermes IA — Asistente ARGOS"
             aria-modal="false">
          <HermesChat apiBase={apiBase} token={token} onClose={handleClose} />
        </div>
      )}
    </>
  )
}
