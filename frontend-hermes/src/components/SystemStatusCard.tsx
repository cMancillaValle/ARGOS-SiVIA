// SystemStatusCard — muestra el snapshot de salud del sistema
// Barra superior con diseño sobrio y profesional sin emojis

import type { SystemHealthSnapshot } from '../types/hermes'
import { CameraIcon, BellIcon, CheckCircleIcon, AlertTriangleIcon } from './Icons'

interface Props {
  snapshot: SystemHealthSnapshot
}

export function SystemStatusCard({ snapshot }: Props) {
  const isNormal = snapshot.nivel === 'normal'

  return (
    <div className="h-system-bar" role="status" aria-label={`Estado del sistema: ${snapshot.nivel}`}>
      <span className={`nivel-badge ${snapshot.nivel}`}>
        {isNormal ? (
          <CheckCircleIcon width={12} height={12} style={{ marginRight: 4 }} />
        ) : (
          <AlertTriangleIcon width={12} height={12} style={{ marginRight: 4 }} />
        )}
        {snapshot.nivel.toUpperCase()}
      </span>
      <span className="stat" title="Cámaras activas">
        <CameraIcon width={13} height={13} style={{ marginRight: 4, verticalAlign: 'text-bottom' }} />
        {snapshot.camaras_activas}/{snapshot.camaras_total}
      </span>
      {snapshot.camaras_offline > 0 && (
        <span className="stat warning-stat" title="Cámaras offline">
          {snapshot.camaras_offline} offline
        </span>
      )}
      <span className="stat" title="Alertas pendientes">
        <BellIcon width={13} height={13} style={{ marginRight: 4, verticalAlign: 'text-bottom' }} />
        {snapshot.alertas_pendientes}
      </span>
    </div>
  )
}
