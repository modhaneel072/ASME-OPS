import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const here = fileURLToPath(new URL('.', import.meta.url))

// Production bundles are emitted into the Flask static folder and served by the
// `ops_app` blueprint at /app. In development Vite serves the SPA itself and
// proxies API + static requests to the Flask server on :5000 so the session
// cookie is shared.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/static/ops/' : '/',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    outDir: fileURLToPath(new URL('../../static/ops', import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: false },
      '/static': { target: 'http://127.0.0.1:5000', changeOrigin: false },
    },
  },
  root: here,
}))
