import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import cssInjectedByJsPlugin from 'vite-plugin-css-injected-by-js'

export default defineConfig({
  plugins: [
    react(),
    cssInjectedByJsPlugin(),
  ],
  build: {
    lib: {
      entry: 'src/hermes-widget.tsx',
      name: 'HermesWidget',
      formats: ['iife'],
      fileName: () => 'hermes-widget.js'
    },
    // Prevent externalizing React so it gets bundled
    rollupOptions: {
      external: [],
      output: {
        extend: true
      }
    }
  },
  define: {
    // Required to prevent issues with React in an IIFE bundle without process defined
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'production')
  }
})
