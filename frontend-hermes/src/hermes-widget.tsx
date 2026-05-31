import React from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import widgetCss from './styles/widget.css?inline'

class HermesWidget extends HTMLElement {
  private root: any = null;
  private mountPoint: HTMLDivElement | null = null;

  static get observedAttributes() {
    return ['token', 'api-base', 'modulo'];
  }

  connectedCallback() {
    // Create shadow DOM
    const shadow = this.attachShadow({ mode: 'open' })
    
    // Inject styles
    const style = document.createElement('style')
    style.textContent = widgetCss
    shadow.appendChild(style)

    // Create mount point
    this.mountPoint = document.createElement('div')
    shadow.appendChild(this.mountPoint)

    this.root = createRoot(this.mountPoint)
    this.renderApp()
  }

  attributeChangedCallback(_name: string, oldValue: string, newValue: string) {
    if (oldValue !== newValue && this.root) {
      this.renderApp()
    }
  }

  private renderApp() {
    const apiBase = this.getAttribute('api-base') || '/api'
    const token = this.getAttribute('token') || ''
    const modulo = this.getAttribute('modulo') || 'dashboard'

    this.root.render(
      <React.StrictMode>
        <App apiBase={apiBase} token={token} modulo={modulo} />
      </React.StrictMode>
    )
  }

  disconnectedCallback() {
    if (this.root) {
      setTimeout(() => this.root.unmount(), 0)
    }
  }
}

// Define the custom element
if (!customElements.get('hermes-widget')) {
  customElements.define('hermes-widget', HermesWidget)
}
