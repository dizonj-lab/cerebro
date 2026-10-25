import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// base './' so the built site runs from any folder or static host
export default defineConfig({ base: './', plugins: [react(), tailwindcss()], server: { port: 4300 } })
