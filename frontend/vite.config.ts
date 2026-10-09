import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const api = { '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, allowedHosts: true, proxy: api },
  preview: { host: true, port: 4173, allowedHosts: true, proxy: api },
});
