import { Info, Menu, Search, X } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useSetPreference } from '@/api/queries/session'
import { cn } from '@/lib/cn'
import { hasPermission, useSession } from '@/lib/permissions'
import { useChangesPoller } from '@/lib/realtime'
import { IconButton, SkeletonBlock } from '@/ui'
import { ErrorBoundary } from './ErrorBoundary'
import { Sidebar } from './Sidebar'
import styles from './shell.module.css'

const COLLAPSE_KEY = 'asme-ops.sidebar.collapsed'
const CommandPalette = lazy(() => import('@/features/search').then((m) => ({ default: m.CommandPalette })))

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

export function SetupBanner() {
  const session = useSession()
  const setPreference = useSetPreference()
  if (session.setup.completed || session.setup.banner_dismissed) return null
  return (
    <div className={styles.banner} role="region" aria-label="Setup status">
      <Info size={16} className={styles.bannerIcon} aria-hidden="true" />
      <span className={styles.bannerText}>Finish setting up your ASME chapter</span>
      <Link to="/setup" className={styles.bannerLink}>
        Continue Setup
      </Link>
      <IconButton label="Dismiss setup banner" variant="ghost" size="sm" onClick={() => setPreference.mutate({ key: 'setup_banner_dismissed', value: true })} loading={setPreference.isPending}>
        <X size={16} />
      </IconButton>
    </div>
  )
}

export function AppShell() {
  const session = useSession()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [lastPath, setLastPath] = useState(location.pathname)
  if (lastPath !== location.pathname) {
    // Close the drawer whenever the route changes (adjusting state during render avoids a cascading effect).
    setLastPath(location.pathname)
    if (mobileOpen) setMobileOpen(false)
  }
  const [paletteOpen, setPaletteOpen] = useState(false)
  useChangesPoller(session)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((open) => !open)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const toggleCollapsed = useCallback(() => {
    setCollapsed((current) => {
      const next = !current
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? '1' : '0')
      } catch {
        /* storage unavailable */
      }
      return next
    })
  }, [])

  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [mobileOpen])

  const showBanner = !session.setup.completed && !session.setup.banner_dismissed && hasPermission(session, 'chapter.setup.manage')

  return (
    <div className={styles.shell}>
      <Sidebar collapsed={collapsed} onToggleCollapsed={toggleCollapsed} mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
      {mobileOpen && <div className={styles.overlay} onClick={() => setMobileOpen(false)} aria-hidden="true" />}
      <div className={cn(styles.main, collapsed && styles.main_collapsed)}>
        <div className={styles.topbar}>
          <IconButton label="Open navigation" variant="ghost" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </IconButton>
          <span className={styles.topbarTitle}>ASME Ops</span>
          <IconButton label="Search (Ctrl+K)" variant="ghost" onClick={() => setPaletteOpen(true)}>
            <Search size={20} />
          </IconButton>
        </div>
        {showBanner && <SetupBanner />}
        <main className={styles.content} id="main">
          <ErrorBoundary key={location.pathname}>
            <Suspense
              fallback={
                <div style={{ padding: 'var(--space-6)' }}>
                  <SkeletonBlock lines={4} />
                </div>
              }
            >
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      {paletteOpen && (
        <Suspense fallback={null}>
          <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        </Suspense>
      )}
    </div>
  )
}
