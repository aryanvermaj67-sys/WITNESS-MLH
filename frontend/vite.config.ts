import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: the browser talks to this server and /api is forwarded to the backend, so no CORS or IP setup is needed.
// Build: the app is served by the backend itself (same origin), so VITE_API_BASE stays empty.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { port: 5173, proxy: { '/api': 'http://127.0.0.1:8000' } },
})
