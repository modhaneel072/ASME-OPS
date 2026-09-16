/**
 * Writes the Netlify `_redirects` and `_headers` files into the built bundle.
 *
 * Netlify serves static files only, so two things have to be arranged here:
 *
 * 1. Routing. The SPA lives under /app (its router basename, and the path the
 *    backend puts in reset-password and invite links), so every /app/* URL has
 *    to return index.html and let the router decide. / sends people to /app.
 * 2. The API. The Flask backend runs on its own host; ASME_API_ORIGIN (set in
 *    the Netlify site's environment variables) is proxied under /api so the
 *    browser sees one origin and the session cookie stays first-party. With no
 *    ASME_API_ORIGIN set, the screens still deploy but nobody can sign in, and
 *    the build log says so.
 *
 * Run by `npm run build:netlify`; see netlify.toml.
 */
import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const outDir = resolve(fileURLToPath(new URL('..', import.meta.url)), process.env.VITE_OUT_DIR || '../../netlify-dist')
if (!existsSync(join(outDir, 'index.html'))) {
  console.error(`netlify-postbuild: no index.html in ${outDir}; run the Vite build first.`)
  process.exit(1)
}

// Guard against a mangled VITE_BASE_PATH (a shell that rewrites "/" into a
// filesystem path, a forgotten trailing slash): every asset in index.html must
// be served from the site root, or the deployed page loads nothing.
const html = readFileSync(join(outDir, 'index.html'), 'utf8')
const localRefs = [...html.matchAll(/(?:src|href)="(?!https?:|data:|#|mailto:)([^"]+)"/g)].map(m => m[1])
const badRefs = localRefs.filter(ref => !/^\/(assets\/|[\w.-]+\.\w+$)/.test(ref))
if (badRefs.length) {
  console.error(`netlify-postbuild: index.html references ${badRefs.join(', ')}; expected site-root paths. Set VITE_BASE_PATH=/ for this build.`)
  process.exit(1)
}

const apiOrigin = (process.env.ASME_API_ORIGIN || '').trim().replace(/\/+$/, '')
// https for a real deploy; plain http only for a local backend, which is how
// this bundle is checked before it is pushed.
const originPattern = /^(https:\/\/[^/\s]+|http:\/\/(127\.0\.0\.1|localhost)(:\d+)?)$/
if (apiOrigin && !originPattern.test(apiOrigin)) {
  console.error(`netlify-postbuild: ASME_API_ORIGIN must be an https origin with no path, got "${apiOrigin}".`)
  process.exit(1)
}

const rules = []
if (apiOrigin) {
  // force = true so the proxy wins over the SPA fallback below.
  rules.push(`/api/*  ${apiOrigin}/api/:splat  200!`)
  rules.push(`/healthz  ${apiOrigin}/healthz  200!`)
} else {
  console.warn('netlify-postbuild: ASME_API_ORIGIN is not set, so this deploy has no backend. Sign-in will fail until you set it.')
}
rules.push('/app/*  /index.html  200')
rules.push('/  /app/  302')
rules.push('/*  /app/  302')
writeFileSync(join(outDir, '_redirects'), rules.join('\n') + '\n', 'utf8')

const headers = `/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
  Cross-Origin-Opener-Policy: same-origin

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/app/*
  Cache-Control: no-store
`
writeFileSync(join(outDir, '_headers'), headers, 'utf8')

// Keep the generated files out of any future asset manifest diffing surprises.
if (existsSync(join(outDir, '.gitignore'))) appendFileSync(join(outDir, '.gitignore'), '\n_redirects\n_headers\n')

console.log(`netlify-postbuild: wrote _redirects (${rules.length} rules) and _headers into ${outDir}`)
