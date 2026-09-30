import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Localhost only. 5173 and 5174 are taken by existing apps; we own 5175.
// strictPort: fail loudly rather than silently hopping to another port.
export default defineConfig({
  plugins: [react()],
  server: { port: 5175, strictPort: true },
  preview: { port: 5175, strictPort: true },
})
