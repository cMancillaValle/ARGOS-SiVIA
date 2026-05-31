// SystemStatusCard — muestra el snapshot de salud del sistema
// aparece en la barra superior del widget

import type { SystemHealthSnapshot } from '../types/hermes'

interface Props {
  snapshot: SystemHealthSnapshot
}

export function SystemStatusCard({ snapshot }: Props) {
  const icons = { normal: '✅', warning: '⚠️', critical: '🔴' } as const

  return (
    <div className="h-system-bar" role="status" aria-label={`Estado del sistema: ${snapshot.nivel}`}>
      <span className={`nivel-badge ${snapshot.nivel}`}>
        {icons[snapshot.nivel]} {snapshot.nivel}
      </span>
      <span className="stat" title="Cámaras activas">
        📷 {snapshot.camaras_activas}/{snapshot.camaras_total}
      </span>
      {snapshot.camaras_offline > 0 && (
        <span className="stat" title="Cámaras offline" style={{ color: 'var(--h-warning)' }}>
          ⚡ {snapshot.camaras_offline} offline
        </span>
      )}
      <span className="stat" title="Alertas pendientes">
        🔔 {snapshot.alertas_pendientes}
      </span>
    </div>
  )
}
