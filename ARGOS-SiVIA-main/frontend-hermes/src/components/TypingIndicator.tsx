// TypingIndicator — animación de escritura del bot

export function TypingIndicator() {
  return (
    <div className="h-bubble-row">
      <div className="h-bubble-avatar hermes">🤖</div>
      <div className="h-typing" role="status" aria-label="Hermes está escribiendo">
        <span className="h-typing-dot" />
        <span className="h-typing-dot" />
        <span className="h-typing-dot" />
      </div>
    </div>
  )
}
