import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const here = fileURLToPath(new URL('.', import.meta.url))

// Two production targets, one codebase:
//
// * Flask (default) - the bundle is emitted into the Flask static folder and
//   served by the `ops_app` blueprint at /app, so assets live under
//   /static/ops/.
// * A static host such as Netlify - the bundle is emitted outside the Flask
//   tree and served from the site root, so assets live under /assets/. Set
//   VITE_BASE_PATH=/ and VITE_OUT_DIR=../../netlify-dist (see netlify.toml).
//
// The SPA router basename stays /app in both cases: reset-password and invite
// links the backend sends point at /app/auth/reset-password.
//
// In development Vite serves the SPA itself and proxies API + static requests
// to the Flask server on :5000 so the session cookie is shared.
const basePath = process.env.VITE_BASE_PATH || '/static/ops/'
const outDir = process.env.VITE_OUT_DIR || '../../static/ops'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? basePath : '/',
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    outDir: fileURLToPath(new URL(outDir, import.meta.url)),
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
