import { z } from 'zod'
import { listOf } from './common'

/** Shape from `asme/ops/serializers/notifications.py::notification`. */
export const Notification = z.object({
  id: z.string(),
  type: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  entity_type: z.string().nullable(),
  entity_id: z.string().nullable(),
  read_at: z.string().nullable(),
  created_at: z.string(),
  /** Absolute SPA path including the `/app` prefix, or null when the entity has no screen. */
  href: z.string().nullable(),
})
export type Notification = z.infer<typeof Notification>

/** `GET /notifications` returns the list envelope plus `unread_count` inside the payload. */
export const NotificationList = listOf(Notification).extend({
  unread_count: z.number().optional(),
})
export type NotificationList = z.infer<typeof NotificationList>

export interface NotificationListParams {
  unread?: boolean
  limit?: number
}

export type MarkReadInput = { ids: string[] } | { all: true }

export const MarkReadResult = z.object({ updated: z.number() })
export type MarkReadResult = z.infer<typeof MarkReadResult>

/** Icon family for a notification type (`work_order.assigned`, `project.added`, `system`, ...). */
export type NotificationKind = 'work_order' | 'project' | 'asset' | 'membership' | 'milestone' | 'system'

export function notificationKind(type: string): NotificationKind {
  const family = type.split('.')[0]
  switch (family) {
    case 'work_order':
    case 'project':
    case 'asset':
    case 'membership':
    case 'milestone':
      return family
    default:
      return 'system'
  }
}

/**
 * The API deep links with the `/app` prefix (`/app/work-orders/<id>`); the
 * router is mounted with `basename: '/app'`, so in-app navigation needs the
 * path without it. Anything outside `/app` is returned unchanged.
 */
export function routerPath(href: string): string {
  if (href === '/app') return '/'
  return href.startsWith('/app/') ? href.slice('/app'.length) : href
}

export function isInAppHref(href: string): boolean {
  return href === '/app' || href.startsWith('/app/')
}
