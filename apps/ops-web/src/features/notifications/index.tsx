import { CheckCheck, ClipboardList, Cpu, Flag, FolderKanban, Info, Users } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { isInAppHref, notificationKind, routerPath, type Notification, type NotificationKind } from '@/api/contracts/notifications'
import { useMarkNotificationsRead, useNotifications } from '@/api/queries/notifications'
import { formatDateTime, formatRelative } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import { Button, EmptyState, InlineAlert, LoadMore, Page, PageHeader, SegmentedControl, SkeletonRows, useToast } from '@/ui'
import styles from './notifications.module.css'

type Filter = 'all' | 'unread'

const KIND_ICONS: Record<NotificationKind, typeof Info> = {
  work_order: ClipboardList,
  project: FolderKanban,
  asset: Cpu,
  membership: Users,
  milestone: Flag,
  system: Info,
}

const KIND_LABELS: Record<NotificationKind, string> = {
  work_order: 'Work order',
  project: 'Project',
  asset: 'Asset',
  membership: 'Membership',
  milestone: 'Milestone',
  system: 'System',
}

export default function NotificationsPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canRead = can('notification.read')

  const filter: Filter = params.get('unread') === '1' ? 'unread' : 'all'
  const list = useNotifications({ unread: filter === 'unread' }, { enabled: canRead })
  const markRead = useMarkNotificationsRead()

  const items = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data])
  const lastPage = list.data?.pages[list.data.pages.length - 1]
  const total = list.data?.pages[0]?.total
  const unreadCount = lastPage?.unread_count ?? list.data?.pages[0]?.unread_count ?? 0

  const setFilter = (next: Filter) => {
    const search = new URLSearchParams(params)
    if (next === 'unread') search.set('unread', '1')
    else search.delete('unread')
    setParams(search)
  }

  const markAllRead = async () => {
    try {
      const result = await markRead.mutateAsync({ all: true })
      toast.success(result.updated === 0 ? 'Nothing left to mark' : `Marked ${result.updated} ${result.updated === 1 ? 'notification' : 'notifications'} as read`)
    } catch (error) {
      toast.error('Could not mark notifications as read', errorMessage(error))
    }
  }

  const openNotification = async (notification: Notification) => {
    if (!notification.read_at) {
      try {
        await markRead.mutateAsync({ ids: [notification.id] })
      } catch (error) {
        toast.error('Could not mark this notification as read', errorMessage(error))
      }
    }
    if (!notification.href) return
    if (isInAppHref(notification.href)) navigate(routerPath(notification.href))
    else window.location.assign(notification.href)
  }

  if (!canRead) {
    return (
      <Page>
        <PageHeader title="Notifications" />
        <div className={styles.scroll}>
          <div className={styles.body}>
            <EmptyState illustration="bell" title="Notifications are not available for your role" description="Ask a chapter administrator if you think you should receive notifications." />
          </div>
        </div>
      </Page>
    )
  }

  const content = list.isPending ? (
    <SkeletonRows rows={8} avatar />
  ) : list.isError ? (
    <div className={styles.state}>
      <InlineAlert
        tone="danger"
        title="Notifications could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : items.length === 0 ? (
    filter === 'unread' ? (
      <EmptyState compact illustration="bell" title="You're all caught up" description="No unread notifications right now." action={<Button size="sm" onClick={() => setFilter('all')}>Show all notifications</Button>} />
    ) : (
      <EmptyState compact illustration="bell" title="You're all caught up" description="Assignments, status changes, mentions and reminders from your chapter will show up here." />
    )
  ) : (
    <>
      <ul className={styles.list} aria-label="Notifications">
        {items.map((notification) => (
          <li key={notification.id}>
            <NotificationRow notification={notification} onOpen={() => void openNotification(notification)} />
          </li>
        ))}
      </ul>
      <LoadMore loaded={items.length} total={total} hasMore={Boolean(list.hasNextPage)} loading={list.isFetchingNextPage} onLoadMore={() => void list.fetchNextPage()} />
    </>
  )

  return (
    <Page>
      <PageHeader
        title="Notifications"
        viewSelector={
          <SegmentedControl<Filter>
            label="Show"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'all', label: 'All' },
              { value: 'unread', label: unreadCount > 0 ? `Unread (${unreadCount})` : 'Unread' },
            ]}
          />
        }
        actions={
          <Button leadingIcon={<CheckCheck size={16} />} onClick={() => void markAllRead()} loading={markRead.isPending && markRead.variables !== undefined && 'all' in markRead.variables} disabled={unreadCount === 0 || markRead.isPending}>
            Mark all as read
          </Button>
        }
      />
      <div className={styles.scroll}>
        <div className={styles.body}>
          <div className={styles.panel}>
            <div className={styles.toolbar}>
              <span>{list.data ? `${unreadCount} unread` : ''}</span>
              <span className={styles.toolbarSpacer} />
              {list.isFetching && !list.isPending && !list.isFetchingNextPage && <span aria-live="polite">Updating…</span>}
            </div>
            {content}
          </div>
        </div>
      </div>
    </Page>
  )
}

function NotificationRow({ notification, onOpen }: { notification: Notification; onOpen: () => void }) {
  const kind = notificationKind(notification.type)
  const Icon = KIND_ICONS[kind]
  const unread = !notification.read_at
  return (
    <button type="button" className={`${styles.row} ${unread ? styles.row_unread : ''}`} onClick={onOpen} aria-label={`${unread ? 'Unread: ' : ''}${notification.title}`} data-testid="notification-row" data-unread={unread || undefined}>
      <span className={styles.icon} aria-hidden="true">
        <Icon size={16} />
      </span>
      <span className={styles.content}>
        <span className={styles.titleRow}>
          <span className={styles.title}>{notification.title}</span>
          <time className={styles.time} dateTime={notification.created_at} title={formatDateTime(notification.created_at)}>
            {formatRelative(notification.created_at)}
          </time>
        </span>
        {notification.body && <span className={styles.text}>{notification.body}</span>}
        <span className={styles.meta}>
          <span>{KIND_LABELS[kind]}</span>
          {unread && <span>· Unread</span>}
          {notification.href && <span>· Open</span>}
        </span>
      </span>
      {unread ? <span className={styles.dot} aria-hidden="true" /> : <span className={styles.dotPlaceholder} aria-hidden="true" />}
    </button>
  )
}
