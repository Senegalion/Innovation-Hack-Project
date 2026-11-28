import path from 'node:path'
import basicSsl from '@vitejs/plugin-basic-ssl'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const api = process.env.API_URL ?? 'http://127.0.0.1:8000'
// HTTPS=1 serves the dev server over a self-signed certificate, so phones on the LAN can use the camera and NFC
const https = process.env.HTTPS === '1'

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(https ? [basicSsl()] : [])],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': api,
      '/ws': { target: api.replace('http', 'ws'), ws: true },
    },
  },
})
