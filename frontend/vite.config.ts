import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'LAB_')
  return {
  plugins: [react()],
  resolve: { alias: { '@lab/topology': fileURLToPath(new URL('./src/ReactFlowDiagram.tsx', import.meta.url)) } },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: process.env.LAB_API_URL || env.LAB_API_URL || 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  }
})
