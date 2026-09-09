import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { api } from '../client'
import { MarkReadResult, NotificationList, type MarkReadInput, type NotificationListParams } from '../contracts/notifications'

export const notificationKeys = {
  all: ['notifications'] as const,
  unreadCount: ['notifications', 'unread-count'] as const,
  list: (params: NotificationListParams) => ['notifications', 'list', params] as const,
}

interface NotificationListPayload {
  items: unknown[]
  next_cursor: string | null
  total?: number
  unread_count?: number
}

const DEFAULT_PAGE_SIZE = 25

function readUnreadCount(payload: NotificationListPayload, extras: Record<string, unknown>): number {
  if (typeof payload.unread_count === 'number') return payload.unread_count
  return typeof extras.unread_count === 'number' ? extras.unread_count : 0
}

/** Unread badge for the sidebar; the change-feed poller keeps it fresh. */
export function useUnreadNotificationCount(enabled = true) {
  return useQuery({
    queryKey: notificationKeys.unreadCount,
    queryFn: async () => {
      const { payload, extras } = await api.request<NotificationListPayload>('GET', '/notifications', { params: { unread: 1, limit: 1 } })
      return readUnreadCount(payload, extras)
    },
    enabled,
    staleTime: 30_000,
  })
}

/** Cursor-paged notification list (`GET /notifications?unread=&limit=&cursor=`). */
export function useNotifications(params: NotificationListParams = {}, { enabled = true }: { enabled?: boolean } = {}) {
  const client = useQueryClient()
  return useInfiniteQuery({
    queryKey: notificationKeys.list(params),
    enabled,
    queryFn: async ({ pageParam }) => {
      const { payload, extras } = await api.request<NotificationListPayload>('GET', '/notifications', {
        params: { unread: params.unread ? 1 : undefined, limit: params.limit ?? DEFAULT_PAGE_SIZE, cursor: pageParam || undefined },
      })
      const page = NotificationList.parse({ ...payload, unread_count: readUnreadCount(payload, extras) })
      client.setQueryData(notificationKeys.unreadCount, page.unread_count ?? 0)
      return page
    },
    initialPageParam: '' as string,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

/**
 * `POST /notifications/read` with `{ids}` or `{all: true}`. The unread badge
 * and any cached lists are updated optimistically; the family is invalidated
 * once the server answers so counts settle on the truth.
 */
export function useMarkNotificationsRead() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: MarkReadInput) => MarkReadResult.parse(await api.post('/notifications/read', input)),
    onMutate: async (input) => {
      await client.cancelQueries({ queryKey: notificationKeys.all })
      const previousCount = client.getQueryData<number>(notificationKeys.unreadCount)
      const previousLists = client.getQueriesData<InfiniteData<NotificationList>>({ queryKey: ['notifications', 'list'] })
      const now = new Date().toISOString()
      const ids = 'all' in input ? null : new Set(input.ids)
      let marked = 0
      for (const [key, data] of previousLists) {
        if (!data) continue
        client.setQueryData<InfiniteData<NotificationList>>(key, {
          ...data,
          pages: data.pages.map((page) => ({
            ...page,
            items: page.items.map((item) => {
              if (item.read_at || (ids && !ids.has(item.id))) return item
              marked += 1
              return { ...item, read_at: now }
            }),
          })),
        })
      }
      if (ids === null) client.setQueryData(notificationKeys.unreadCount, 0)
      else if (typeof previousCount === 'number') client.setQueryData(notificationKeys.unreadCount, Math.max(0, previousCount - Math.max(marked, 0)))
      return { previousCount, previousLists }
    },
    onError: (_error, _input, context) => {
      if (!context) return
      if (context.previousCount !== undefined) client.setQueryData(notificationKeys.unreadCount, context.previousCount)
      for (const [key, data] of context.previousLists) client.setQueryData(key, data)
    },
    onSettled: () => client.invalidateQueries({ queryKey: notificationKeys.all }),
  })
}
