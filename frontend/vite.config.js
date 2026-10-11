import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        // Forward API calls to the FastAPI backend during development.
        // Set VITE_PROXY_TARGET in frontend/.env if the backend runs on another port.
        '/api': env.VITE_PROXY_TARGET || 'http://localhost:8000',
      },
    },
  }
})
