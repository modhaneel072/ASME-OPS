/**
 * The API returns absolute app paths such as `/app/locations`, while the router
 * is mounted with `basename: '/app'`. Router links need the path without the
 * base, otherwise they resolve to `/app/app/...`.
 *
 * Candidate for promotion to `src/lib` once another feature needs it
 * (audit-event and notification `href`s use the same shape).
 */
export const APP_BASENAME = '/app'

export function appPath(href: string): string {
  if (href === APP_BASENAME) return '/'
  if (href.startsWith(`${APP_BASENAME}/`)) return href.slice(APP_BASENAME.length)
  return href
}
