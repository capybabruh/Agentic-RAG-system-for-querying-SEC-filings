import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  preview: {
    // Railway's domain isn't known at build time (and can change), so allow
    // any host rather than hardcoding one — the preview server sits behind
    // Railway's own edge routing, not exposed as a general-purpose dev server.
    allowedHosts: true,
  },
})
