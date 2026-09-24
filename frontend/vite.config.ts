import { defineConfig } from 'vite'

const api = 'http://127.0.0.1:8766'

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/session': { target: api, changeOrigin: true },
      '/health': { target: api, changeOrigin: true },
      '/jobs': { target: api, changeOrigin: true },
      '/clients': { target: api, changeOrigin: true },
      '/evidence': { target: api, changeOrigin: true },
      '/reporting': { target: api, changeOrigin: true },
      '/settings': { target: api, changeOrigin: true },
      '/openapi.json': { target: api, changeOrigin: true },
    },
  },
})
