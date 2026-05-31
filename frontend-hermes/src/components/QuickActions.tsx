// QuickActions — botones de acción rápida contextual por rol

import type { AccionSugerida } from '../types/hermes'

interface Props {
  acciones: AccionSugerida[]
}

export function QuickActions({ acciones }: Props) {
  if (!acciones.length) return null

  const handleClick = (accion: AccionSugerida) => {
    // En la versión actual abrimos el endpoint en una nueva pestaña
    // En futuras versiones puede despachar a la vista del dashboard
    if (accion.endpoint) {
      const baseUrl = window.location.origin
      window.open(`${baseUrl}${accion.endpoint}`, '_blank', 'noopener')
    }
  }

  return (
    <div className="h-quick-actions" role="group" aria-label="Acciones rápidas">
      {acciones.map((a) => (
        <button
          key={a.id}
          id={`hermes-action-${a.id}`}
          className="h-action-btn"
          onClick={() => handleClick(a)}
          title={a.permiso_requerido ? `Requiere: ${a.permiso_requerido}` : a.label}
        >
          {a.label}
        </button>
      ))}
    </div>
  )
}
