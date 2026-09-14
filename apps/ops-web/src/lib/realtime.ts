import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api, ApiError } from '@/api/client'
import type { AuditEvent } from '@/api/contracts/common'
import type { Session } from '@/api/contracts/session'

interface ChangesPayload {
  events: AuditEvent[]
  now: string
  unread_notifications?: number
  has_more?: boolean
}

/** Which query families to revalidate when an entity of a given type changes. */
const INVALIDATIONS: Record<string, string[][]> = {
  work_order: [['work-orders'], ['projects'], ['reports'], ['search']],
  project: [['projects'], ['work-orders']],
  milestone: [['projects']],
  asset: [['assets'], ['projects']],
  location: [['locations'], ['assets']],
  category: [['categories'], ['work-orders']],
  team: [['teams'], ['users']],
  membership: [['users'], ['teams'], ['session']],
  comment: [['comments']],
  attachment: [['attachments']],
  organization: [['session'], ['setup']],
  vendor: [['vendors']],
  saved_filter: [['saved-filters']],
}

/**
 * Polls `/api/v1/changes` while the tab is visible and invalidates the query
 * families touched by each change. This is the "reliable fallback" transport;
 * a push channel can replace the timer without changing consumers.
 */
export function useChangesPoller(session: Session | null) {
  const client = useQueryClient()
  const since = useRef<string>(new Date().toISOString())
  const disabled = useRef(false)

  useEffect(() => {
    if (!session) return
    const interval = Math.max(3, session.features.poll_seconds) * 1000
    let cancelled = false
    let timer = 0

    const tick = async () => {
      if (cancelled || disabled.current) return
      if (document.visibilityState !== 'visible') return schedule()
      try {
        const payload = await api.get<ChangesPayload>('/changes', { params: { since: since.current, limit: 100 } })
        since.current = payload.now
        const families = new Set<string>()
        for (const event of payload.events) {
          for (const key of INVALIDATIONS[event.entity_type] ?? []) families.add(JSON.stringify(key))
        }
        if (payload.events.length) families.add(JSON.stringify(['changes']))
        families.add(JSON.stringify(['notifications']))
        for (const family of families) void client.invalidateQueries({ queryKey: JSON.parse(family) as string[] })
        if (payload.unread_notifications !== undefined) client.setQueryData(['notifications', 'unread-count'], payload.unread_notifications)
      } catch (error) {
        if (error instanceof ApiError && (error.isAuth || error.isNotFound)) {
          // Logged out, or the change feed is not deployed: stop polling for this session.
          disabled.current = error.isNotFound
          if (error.isAuth) void client.invalidateQueries({ queryKey: ['session'] })
          return
        }
      } finally {
        schedule()
      }
    }
    const schedule = () => {
      if (cancelled || disabled.current) return
      timer = window.setTimeout(() => void tick(), interval)
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        window.clearTimeout(timer)
        void tick()
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    schedule()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [session, client])
}
