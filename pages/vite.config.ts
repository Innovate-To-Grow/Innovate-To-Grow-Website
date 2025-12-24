import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')
  
  // Backend API URL - defaults to localhost:8000 for development
  const backendUrl = env.VITE_BACKEND_URL || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/health': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/pages': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/layout': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/notify': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/authn': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/media': {
          target: backendUrl,
          changeOrigin: true,
        },
        '/admin': {
          target: backendUrl,
          changeOrigin: true,
        },
        // Note: /static/images is served from pages/public/static/images locally
      },
    },
  }
})
