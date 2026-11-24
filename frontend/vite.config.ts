import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const api = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, strictPort: true, allowedHosts: true, proxy: api },
  preview: { host: true, port: 4173, allowedHosts: true, proxy: api },
});
