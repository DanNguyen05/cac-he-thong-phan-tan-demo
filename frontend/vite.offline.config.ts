import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [react()],
  define: { 'import.meta.env.VITE_DEFAULT_RENDERER': JSON.stringify('svg') },
  resolve: { alias: { '@lab/topology': fileURLToPath(new URL('./src/OfflineDiagram.tsx', import.meta.url)) } },
})
