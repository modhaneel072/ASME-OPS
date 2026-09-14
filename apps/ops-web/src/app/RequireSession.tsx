import { LogOut } from 'lucide-react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { useLogout, useSessionQuery, useSessionState } from '@/api/queries/session'
import { SessionContext } from '@/lib/permissions'
import { Button, InlineAlert, SkeletonBlock } from '@/ui'
import styles from './shell.module.css'

export function RequireSession() {
  const state = useSessionState()
  const query = useSessionQuery()
  const location = useLocation()
  const navigate = useNavigate()
  const logout = useLogout()

  if (state.status === 'loading') {
    return (
      <div className={styles.shell}>
        <div className={styles.centered} aria-busy="true" aria-label="Loading ASME Ops">
          <div style={{ width: 320 }}>
            <SkeletonBlock lines={4} />
          </div>
        </div>
      </div>
    )
  }
  if (state.status === 'anonymous') {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/auth/login?next=${encodeURIComponent(next)}`} replace />
  }
  if (state.status === 'no_membership') {
    return (
      <div className={styles.shell}>
        <div className={styles.centered}>
          <div className={styles.authCard}>
            <h1 className={styles.authTitle}>You are signed in, but not a member of this workspace</h1>
            <p className={styles.authSubtitle} style={{ marginTop: 8 }}>
              Your account is not an active member of the ASME Ops workspace for this chapter. Ask a chapter administrator to invite you or reactivate your membership.
            </p>
            <div style={{ display: 'flex', gap: 8, marginTop: 24 }}>
              <Button variant="primary" leadingIcon={<LogOut size={16} />} onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/auth/login', { replace: true }) })}>
                Log out
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  }
  if (state.status === 'error') {
    return (
      <div className={styles.shell}>
        <div className={styles.centered}>
          <div style={{ maxWidth: 480, width: '100%' }}>
            <InlineAlert
              tone="danger"
              title="ASME Ops could not load your session"
              actions={
                <Button size="sm" onClick={() => void query.refetch()} loading={query.isFetching}>
                  Retry
                </Button>
              }
            >
              {errorMessage(state.error)}
            </InlineAlert>
          </div>
        </div>
      </div>
    )
  }
  return (
    <SessionContext.Provider value={state.session}>
      <Outlet />
    </SessionContext.Provider>
  )
}
