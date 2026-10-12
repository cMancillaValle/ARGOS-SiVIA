// TypingIndicator — indicador de progreso textual basado en etapas reales

import { useState, useEffect } from 'react'
import { BotIcon } from './Icons'

interface Props {
  query?: string
}

export function TypingIndicator({ query = '' }: Props) {
  const [etapaTexto, setEtapaTexto] = useState('Clasificando consulta')

  useEffect(() => {
    const q = query.toLowerCase()

    // Secuencia honesta basada en el tipo de consulta
    let paso2 = 'Consultando datos'
    if (q.includes('evento') || q.includes('alerta') || q.includes('detecc')) {
      paso2 = 'Consultando eventos'
    } else if (q.includes('camara') || q.includes('cámara') || q.includes('chavi')) {
      paso2 = 'Consultando cámaras'
    } else if (q.includes('cpu') || q.includes('ram') || q.includes('disco') || q.includes('red') || q.includes('infraestructura')) {
      paso2 = 'Consultando métricas de infraestructura'
    } else if (q.includes('usuario')) {
      paso2 = 'Consultando usuarios'
    } else if (q.includes('auditoria') || q.includes('auditoría')) {
      paso2 = 'Consultando auditoría'
    } else if (q.includes('tripwire') || q.includes('athena') || q.includes('como funciona')) {
      paso2 = 'Buscando documentación'
    }

    setEtapaTexto('Clasificando consulta')

    const timer1 = setTimeout(() => {
      setEtapaTexto(paso2)
    }, 450)

    const timer2 = setTimeout(() => {
      if (paso2 === 'Buscando documentación' || q.includes('explica') || q.includes('significa')) {
        setEtapaTexto('Generando explicación')
      } else {
        setEtapaTexto('Preparando respuesta')
      }
    }, 1100)

    return () => {
      clearTimeout(timer1)
      clearTimeout(timer2)
    }
  }, [query])

  return (
    <div className="h-bubble-row">
      <div className="h-bubble-avatar hermes" aria-hidden>
        <BotIcon width={16} height={16} />
      </div>
      <div className="h-typing" role="status" aria-label={etapaTexto}>
        <span className="h-typing-stage-text">{etapaTexto}</span>
        <span className="h-typing-dots">
          <span className="h-typing-dot" />
          <span className="h-typing-dot" />
          <span className="h-typing-dot" />
        </span>
      </div>
    </div>
  )
}
