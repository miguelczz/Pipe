import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

export default defineConfig({
  plugins: [react()],
  base: '/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy de las rutas API al backend.
    // bypass: si el navegador pide HTML (navegación), Vite sirve la SPA.
    // Solo las llamadas fetch/XHR (Accept: application/json) van al backend.
    proxy: {
      '/api': {
        target: 'http://pipe-backend:8000',
        changeOrigin: true,
      },
      '/agent': {
        target: 'http://pipe-backend:8000',
      },
      '/files': {
        target: 'http://pipe-backend:8000',
        bypass(req) {
          if (req.headers.accept && req.headers.accept.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '/tools': {
        target: 'http://pipe-backend:8000',
      },
      '/reports': {
        target: 'http://pipe-backend:8000',
        bypass(req) {
          if (req.headers.accept && req.headers.accept.includes('text/html')) {
            return '/index.html'
          }
        },
      },
      '/network-analysis': {
        target: 'http://pipe-backend:8000',
        bypass(req) {
          if (req.headers.accept && req.headers.accept.includes('text/html')) {
            return '/index.html'
          }
        },
      },
    },
  },
})
