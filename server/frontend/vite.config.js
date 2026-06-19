import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dashboard UI is operator-only: bind strictly to loopback.
    // This prevents LAN devices from opening the admin interface
    // even during development (where host:true / host:"0.0.0.0" is
    // a common but dangerous default).
    host: '127.0.0.1',
    port: 5173,
  },
})
