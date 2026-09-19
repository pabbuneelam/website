import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API has no path prefix (/attributes, /slates, /cards, /users, /health
// live at the root), so dev proxies those exact prefixes straight to uvicorn
// instead of routing everything through one catch-all -- that would also
// swallow Vite's own dev endpoints.
const API_TARGET = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/attributes': API_TARGET,
      '/slates': API_TARGET,
      '/cards': API_TARGET,
      '/users': API_TARGET,
      '/health': API_TARGET,
    },
  },
})
