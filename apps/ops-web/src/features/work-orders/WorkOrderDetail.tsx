import { Check, Copy, Eye, EyeOff, GitBranch, Link2, MoreHorizontal, Pause, Pencil, Play, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { isImageAttachment } from '@/api/contracts/attachments'
import { COST_TYPE_LABELS, type CompleteResponse, type CostType, type StatusHistoryEntry, type WorkOrderDetail as WorkOrderDetailShape } from '@/api/contracts/work-orders'
import { useAttachments } from '@/api/queries/attachments'
import { useComments } from '@/api/queries/comments'
import { useDeleteCostEntry, useDeleteTimeEntry, useDuplicateWorkOrder, useRemoveDependency, useTransitionWorkOrder, useWatchWorkOrder } from '@/api/queries/work-orders'
import { formatDate, formatDateTime, formatMinutes, formatMoney } from '@/lib/dates'
import { canOn, useCan, useSession } from '@/lib/permissions'
import { ActivityTimeline, Avatar, Button, Card, CategoryChip, DetailPanel, DropdownMenu, EmptyState, FieldList, Grid2, IconButton, InlineAlert, ListRow, PriorityBadge, Stack, StatusBadge, useToast, type TimelineItem } from '@/ui'
import { CommentsCard } from './CommentsCard'
import { CompleteDialog } from './CompleteDialog'
import { AddCostDialog, AssigneesDialog, CancelDialog, DependencyDialog, LogTimeDialog, WatchersDialog } from './DetailDialogs'
import { FilesCard } from './FilesCard'
import { PartsReadinessBadge, WorkOrderPartsSection } from './WorkOrderPartsSection'
import { DueLabel, workTypeLabel } from './WorkOrderList'
import styles from './work-orders.module.css'

export interface WorkOrderDetailProps {
  workOrder: WorkOrderDetailShape
  /** `?query` preserving the list state, appended to internal links. */
  listSearch: string
}

type DialogKind = 'complete' | 'cancel' | 'assignees' | 'watchers' | 'dependency' | 'time' | 'cost' | null

const TRANSITION_TITLES: Record<string, string> = {
  'null->open': 'Opened',
  'null->draft': 'Drafted',
  'draft->open': 'Published',
  'open->in_progress': 'Started',
  'in_progress->on_hold': 'Put on hold',
  'on_hold->in_progress': 'Resumed',
  'open->done': 'Completed',
  'in_progress->done': 'Completed',
  'open->canceled': 'Canceled',
  'in_progress->canceled': 'Canceled',
  'on_hold->canceled': 'Canceled',
  'done->open': 'Reopened',
  'canceled->open': 'Reopened',
}

export function historyTitle(entry: StatusHistoryEntry): string {
  return TRANSITION_TITLES[`${entry.from_status ?? 'null'}->${entry.to_status}`] ?? `Moved to ${entry.to_status.replace(/_/g, ' ')}`
}

export function WorkOrderDetail({ workOrder: wo, listSearch }: WorkOrderDetailProps) {
  const session = useSession()
  const can = useCan()
  const toast = useToast()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState<DialogKind>(null)

  const transition = useTransitionWorkOrder(wo.id)
  const duplicate = useDuplicateWorkOrder()
  const watch = useWatchWorkOrder(wo.id)
  const removeDependency = useRemoveDependency(wo.id)
  const deleteTime = useDeleteTimeEntry(wo.id)
  const deleteCost = useDeleteCostEntry(wo.id)
  const attachments = useAttachments('work-orders', wo.id)
  const comments = useComments('work-orders', wo.id)

  const canStart = canOn(session, 'work_order.start', wo)
  const canComplete = canOn(session, 'work_order.complete', wo)
  const canCancel = canOn(session, 'work_order.cancel', wo)
  const canEdit = canOn(session, 'work_order.edit', wo)
  const canAssign = canOn(session, 'work_order.assign', wo)
  const canLogTime = canOn(session, 'work_order.log_time', wo)
  const canCreate = can('work_order.create')
  const watching = wo.watchers.some((u) => u.id === session.user.id)
  const busy = transition.isPending

  const run = async (action: 'start' | 'hold' | 'resume' | 'reopen', label: string) => {
    try {
      await transition.mutateAsync({ action })
      toast.success(`#${wo.number} ${label}`)
    } catch (error) {
      toast.error(`Could not ${action === 'hold' ? 'put on hold' : action} #${wo.number}`, errorMessage(error))
    }
  }

  const onDuplicate = async () => {
    try {
      const copy = await duplicate.mutateAsync(wo.id)
      toast.success(`#${copy.number} created`, `Duplicated from #${wo.number}`)
      navigate(`/work-orders/${copy.id}${listSearch}`)
    } catch (error) {
      toast.error('Could not duplicate the work order', errorMessage(error))
    }
  }

  const onWatch = async () => {
    try {
      await watch.mutateAsync(!watching)
      toast.success(watching ? `Stopped watching #${wo.number}` : `Watching #${wo.number}`)
    } catch (error) {
      toast.error('Could not update watching', errorMessage(error))
    }
  }

  const onCopyLink = async () => {
    const url = `${window.location.origin}/app/work-orders/${wo.id}`
    try {
      await navigator.clipboard.writeText(url)
      toast.success('Link copied', url)
    } catch {
      toast.info('Copy this link', url)
    }
  }

  const onCompleted = (result: CompleteResponse) => {
    if (result.follow_up) navigate(`/work-orders/${result.follow_up.id}${listSearch}`)
  }

  const status = wo.status
  const actions: ReactNode[] = []
  if (status === 'open' && canStart) {
    actions.push(
      <Button key="start" variant="primary" leadingIcon={<Play size={16} />} onClick={() => void run('start', 'started')} disabled={busy || wo.is_blocked} title={wo.is_blocked ? 'Blocked by dependencies' : undefined}>
        Start
      </Button>,
    )
  }
  if (status === 'in_progress' && canStart) {
    actions.push(
      <Button key="hold" leadingIcon={<Pause size={16} />} onClick={() => void run('hold', 'put on hold')} disabled={busy}>
        Put On Hold
      </Button>,
    )
  }
  if (status === 'on_hold' && canStart) {
    actions.push(
      <Button key="resume" variant="primary" leadingIcon={<Play size={16} />} onClick={() => void run('resume', 'resumed')} disabled={busy}>
        Resume
      </Button>,
    )
  }
  if ((status === 'open' || status === 'in_progress') && canComplete) {
    actions.push(
      <Button key="complete" variant={status === 'in_progress' ? 'primary' : 'secondary'} leadingIcon={<Check size={16} />} onClick={() => setDialog('complete')} disabled={busy}>
        Complete
      </Button>,
    )
  }
  if ((status === 'done' || status === 'canceled') && canEdit) {
    actions.push(
      <Button key="reopen" leadingIcon={<RotateCcw size={16} />} onClick={() => void run('reopen', 'reopened')} disabled={busy}>
        Reopen
      </Button>,
    )
  }
  if (canEdit) {
    actions.push(
      <Button key="edit" leadingIcon={<Pencil size={16} />} onClick={() => navigate(`/work-orders/${wo.id}/edit${listSearch}`)}>
        Edit
      </Button>,
    )
  }
  const menuItems = [
    ...(canCreate
      ? [
          { key: 'duplicate', label: 'Duplicate', icon: <Copy size={16} />, onSelect: () => void onDuplicate(), disabled: duplicate.isPending },
          { key: 'sub', label: 'Add sub-work order', icon: <GitBranch size={16} />, onSelect: () => navigate(`/work-orders/new${listSearch ? `${listSearch}&` : '?'}parent=${wo.id}`) },
        ]
      : []),
    { key: 'watch', label: watching ? 'Stop watching' : 'Watch', icon: watching ? <EyeOff size={16} /> : <Eye size={16} />, onSelect: () => void onWatch(), disabled: watch.isPending },
    { key: 'link', label: 'Copy link', icon: <Link2 size={16} />, onSelect: () => void onCopyLink() },
    ...((status === 'open' || status === 'in_progress' || status === 'on_hold') && canCancel
      ? [
          { key: 'sep', type: 'separator' as const },
          { key: 'cancel', label: 'Cancel work order', icon: <X size={16} />, destructive: true, onSelect: () => setDialog('cancel') },
        ]
      : []),
  ]

  const images = (attachments.data?.items ?? []).filter(isImageAttachment)
  const totalMinutes = wo.time_entries.reduce((sum, e) => sum + e.minutes, 0)
  const totalCost = wo.cost_entries.reduce((sum, e) => sum + (e.amount ?? 0), 0)
  const timeline: TimelineItem[] = [...wo.status_history]
    .sort((a, b) => (a.changed_at < b.changed_at ? 1 : -1))
    .map((entry) => ({ id: entry.id, title: historyTitle(entry), actor: entry.changed_by?.name ?? null, at: entry.changed_at, content: entry.note || undefined }))

  const blockers = wo.dependencies.blocked_by.filter((dep) => !['done', 'canceled', 'skipped'].includes(dep.work_order.status))

  return (
    <DetailPanel
      eyebrow={
        <span className={styles.eyebrow}>
          <span className="mono">#{wo.number}</span>
          <span aria-hidden="true">·</span>
          <span>{workTypeLabel(wo.work_type)}</span>
          {wo.project && (
            <>
              <span aria-hidden="true">·</span>
              <Link to={`/projects/${wo.project.id}`}>{wo.project.code}</Link>
            </>
          )}
          {wo.parent_id && (
            <>
              <span aria-hidden="true">·</span>
              <Link to={`/work-orders/${wo.parent_id}${listSearch}`}>Sub-work order of #{wo.parent_number}</Link>
            </>
          )}
        </span>
      }
      title={wo.title}
      subtitle={
        <span className={styles.badges}>
          <StatusBadge status={wo.status} />
          <PriorityBadge priority={wo.priority} />
          <PartsReadinessBadge workOrderId={wo.id} />
          <DueLabel workOrder={wo} />
        </span>
      }
      actions={
        <>
          {actions}
          <DropdownMenu
            align="end"
            label="More actions"
            items={menuItems}
            trigger={(props) => (
              <IconButton {...props} ref={props.ref} label="More actions">
                <MoreHorizontal size={18} />
              </IconButton>
            )}
          />
        </>
      }
    >
      <Stack>
        {wo.is_blocked && blockers.length > 0 && (
          <InlineAlert tone="warning" title="Blocked by dependencies">
            This work order cannot start until {blockers.map((dep, i) => (
              <span key={dep.id}>
                {i > 0 && ', '}
                <Link to={`/work-orders/${dep.work_order.id}${listSearch}`}>#{dep.work_order.number}</Link>
              </span>
            ))}{' '}
            {blockers.length === 1 ? 'is' : 'are'} done or canceled.
          </InlineAlert>
        )}
        {wo.status === 'draft' && canEdit && (
          <InlineAlert tone="info" title="This is a draft" actions={<Button size="sm" onClick={() => navigate(`/work-orders/${wo.id}/edit${listSearch}`)}>Edit and publish</Button>}>
            Drafts are only visible in the To Do list and do not notify anyone until published.
          </InlineAlert>
        )}

        <Card title="Description">
          {wo.description ? <p className={styles.description}>{wo.description}</p> : <p className={styles.muted}>No description.</p>}
          {images.length > 0 && (
            <div className={styles.thumbs}>
              {images.map((image) => (
                <a key={image.id} href={image.download_url} className={styles.thumb} title={image.original_name}>
                  <img src={image.download_url} alt={image.original_name} loading="lazy" />
                </a>
              ))}
            </div>
          )}
          {wo.completion_note && (
            <div style={{ marginTop: 'var(--space-4)' }}>
              <p className={styles.sectionLabel}>Completion note</p>
              <p className={styles.description}>{wo.completion_note}</p>
            </div>
          )}
        </Card>

        <Grid2>
          <Card title="Details">
            <FieldList
              items={[
                { label: 'Project', value: wo.project ? <Link to={`/projects/${wo.project.id}`}>{wo.project.name}</Link> : '—' },
                { label: 'Location', value: wo.location ? <Link to={`/locations/${wo.location.id}`}>{wo.location.name}</Link> : '—' },
                {
                  label: 'Asset',
                  value: wo.asset ? (
                    <span className={styles.chips}>
                      <Link to={`/assets/${wo.asset.id}`}>{wo.asset.name}</Link>
                      {wo.related_assets.map((asset) => (
                        <Link key={asset.id} to={`/assets/${asset.id}`} className={styles.teamChip}>
                          {asset.name}
                        </Link>
                      ))}
                    </span>
                  ) : (
                    '—'
                  ),
                },
                { label: 'Team', value: wo.team?.name ?? '—' },
                { label: 'Vendor', value: wo.vendor?.name ?? '—' },
                {
                  label: 'Categories',
                  value: wo.categories.length ? (
                    <span className={styles.chips}>
                      {wo.categories.map((c) => (
                        <CategoryChip key={c.id} name={c.name} color={c.color} size="sm" />
                      ))}
                    </span>
                  ) : (
                    '—'
                  ),
                },
                { label: 'Work type', value: workTypeLabel(wo.work_type) },
                { label: 'Created by', value: wo.created_by ? `${wo.created_by.name} · ${formatDateTime(wo.created_at)}` : formatDateTime(wo.created_at) },
                { label: 'Budget code', value: wo.budget_code ? <span className="mono">{wo.budget_code}</span> : '—' },
              ]}
            />
          </Card>
          <Card title="Schedule">
            <FieldList
              items={[
                { label: 'Start', value: formatDateTime(wo.start_at) },
                { label: 'Due', value: wo.due_at ? <span className={styles.chips}>{formatDateTime(wo.due_at)}</span> : '—' },
                { label: 'Completed', value: formatDateTime(wo.completed_at) },
                { label: 'Estimated', value: wo.estimated_minutes ? formatMinutes(wo.estimated_minutes) : '—' },
                { label: 'Actual', value: wo.actual_minutes ? formatMinutes(wo.actual_minutes) : '0m' },
                { label: 'Updated', value: formatDateTime(wo.updated_at) },
              ]}
            />
          </Card>
        </Grid2>

        <Card
          title="People"
          actions={
            canAssign ? (
              <span className={styles.cardActions}>
                <Button size="sm" variant="ghost" leadingIcon={<Pencil size={14} />} onClick={() => setDialog('assignees')}>
                  Edit assignees
                </Button>
                <Button size="sm" variant="ghost" leadingIcon={<Pencil size={14} />} onClick={() => setDialog('watchers')}>
                  Edit watchers
                </Button>
              </span>
            ) : undefined
          }
        >
          <Grid2>
            <div>
              <p className={styles.sectionLabel}>Assignees</p>
              {wo.assignees.length === 0 && wo.assignee_teams.length === 0 ? (
                <p className={styles.muted}>Unassigned</p>
              ) : (
                <div className={styles.people}>
                  {wo.assignees.map((user) => (
                    <span key={user.id} className={styles.person}>
                      <Avatar name={user.name} src={user.avatar_url} />
                      <span>{user.name}</span>
                    </span>
                  ))}
                  {wo.assignee_teams.map((team) => (
                    <span key={team.id} className={styles.person}>
                      <span className={styles.teamChip}>{team.name}</span>
                      <span className={styles.personMeta}>team</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div>
              <p className={styles.sectionLabel}>Watchers</p>
              {wo.watchers.length === 0 ? (
                <p className={styles.muted}>No watchers</p>
              ) : (
                <div className={styles.people}>
                  {wo.watchers.map((user) => (
                    <span key={user.id} className={styles.person}>
                      <Avatar name={user.name} src={user.avatar_url} />
                      <span>{user.name}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </Grid2>
        </Card>

        <Card
          title={`Sub-work orders (${wo.sub_work_orders.done}/${wo.sub_work_orders.total})`}
          flush
          actions={
            <span className={styles.cardActions}>
              {wo.children.length > 0 && <span className={styles.personMeta}>Parent completes {wo.parent_completion_policy === 'auto' ? 'automatically when all are done' : 'manually'}</span>}
              {canCreate && (
                <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => navigate(`/work-orders/new${listSearch ? `${listSearch}&` : '?'}parent=${wo.id}`)}>
                  Add
                </Button>
              )}
            </span>
          }
        >
          {wo.children.length === 0 ? (
            <EmptyState compact illustration="clipboard" title="No sub-work orders" description="Break larger work into smaller pieces that can be assigned separately." />
          ) : (
            <ul aria-label="Sub-work orders">
              {wo.children.map((child) => (
                <li key={child.id}>
                  <ListRow compact to={`/work-orders/${child.id}${listSearch}`} leading={<span className={styles.number}>#{child.number}</span>} title={child.title} meta={<DueLabel workOrder={child} compact />} trailing={<StatusBadge status={child.status} size="sm" />} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="Dependencies"
          actions={
            canEdit ? (
              <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => setDialog('dependency')}>
                Add dependency
              </Button>
            ) : undefined
          }
        >
          <div className={styles.blockGroup}>
            <p className={styles.sectionLabel}>Blocked by</p>
            {wo.dependencies.blocked_by.length === 0 ? (
              <p className={styles.muted}>Nothing blocks this work order.</p>
            ) : (
              <ul aria-label="Blocked by">
                {wo.dependencies.blocked_by.map((dep) => (
                  <li key={dep.id} className={styles.depRow}>
                    <span className={styles.number}>#{dep.work_order.number}</span>
                    <Link to={`/work-orders/${dep.work_order.id}${listSearch}`} className={styles.depTitle}>
                      {dep.work_order.title}
                    </Link>
                    <StatusBadge status={dep.work_order.status} size="sm" />
                    {canEdit && (
                      <IconButton
                        size="sm"
                        variant="ghost"
                        label={`Remove dependency on #${dep.work_order.number}`}
                        loading={removeDependency.isPending && removeDependency.variables === dep.id}
                        onClick={async () => {
                          try {
                            await removeDependency.mutateAsync(dep.id)
                            toast.success('Dependency removed')
                          } catch (error) {
                            toast.error('Could not remove the dependency', errorMessage(error))
                          }
                        }}
                      >
                        <Trash2 size={14} />
                      </IconButton>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className={styles.blockGroup}>
            <p className={styles.sectionLabel}>Blocking</p>
            {wo.dependencies.blocking.length === 0 ? (
              <p className={styles.muted}>This work order does not block anything.</p>
            ) : (
              <ul aria-label="Blocking">
                {wo.dependencies.blocking.map((dep) => (
                  <li key={dep.id} className={styles.depRow}>
                    <span className={styles.number}>#{dep.work_order.number}</span>
                    <Link to={`/work-orders/${dep.work_order.id}${listSearch}`} className={styles.depTitle}>
                      {dep.work_order.title}
                    </Link>
                    <StatusBadge status={dep.work_order.status} size="sm" />
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        <WorkOrderPartsSection workOrder={wo} />

        <Card
          title="Time & cost"
          flush
          actions={
            canLogTime ? (
              <span className={styles.cardActions}>
                <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => setDialog('time')}>
                  Log time
                </Button>
                <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => setDialog('cost')}>
                  Add cost
                </Button>
              </span>
            ) : undefined
          }
        >
          <div className={styles.entryTableWrap}>
            <table className={styles.entryTable} aria-label="Time entries">
              <thead>
                <tr>
                  <th scope="col">Person</th>
                  <th scope="col" className={styles.numeric}>
                    Time
                  </th>
                  <th scope="col">Note</th>
                  <th scope="col">Date</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {wo.time_entries.length === 0 ? (
                  <tr>
                    <td colSpan={5} className={styles.muted}>
                      No time logged yet.
                    </td>
                  </tr>
                ) : (
                  wo.time_entries.map((entry) => {
                    const own = entry.user?.id === session.user.id
                    return (
                      <tr key={entry.id}>
                        <td>{entry.user?.name ?? '—'}</td>
                        <td className={styles.numeric}>{formatMinutes(entry.minutes)}</td>
                        <td className="wrap">{entry.note || '—'}</td>
                        <td>{formatDate(entry.started_at ?? entry.created_at)}</td>
                        <td>
                          {(own || canAssign) && canLogTime && (
                            <IconButton
                              size="sm"
                              variant="ghost"
                              label={`Delete time entry of ${formatMinutes(entry.minutes)}`}
                              loading={deleteTime.isPending && deleteTime.variables === entry.id}
                              onClick={async () => {
                                try {
                                  await deleteTime.mutateAsync(entry.id)
                                  toast.success('Time entry deleted')
                                } catch (error) {
                                  toast.error('Could not delete the time entry', errorMessage(error))
                                }
                              }}
                            >
                              <Trash2 size={14} />
                            </IconButton>
                          )}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td className={styles.numeric}>{formatMinutes(totalMinutes)}</td>
                  <td colSpan={3}>{wo.estimated_minutes ? `Estimated ${formatMinutes(wo.estimated_minutes)}` : ''}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <div className={styles.entryTableWrap}>
            <table className={styles.entryTable} aria-label="Cost entries">
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col" className={styles.numeric}>
                    Amount
                  </th>
                  <th scope="col">Vendor</th>
                  <th scope="col">Description</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {wo.cost_entries.length === 0 ? (
                  <tr>
                    <td colSpan={5} className={styles.muted}>
                      No costs recorded.
                    </td>
                  </tr>
                ) : (
                  wo.cost_entries.map((entry) => (
                    <tr key={entry.id}>
                      <td>{COST_TYPE_LABELS[entry.type as CostType] ?? entry.type}</td>
                      <td className={styles.numeric}>{formatMoney(entry.amount)}</td>
                      <td>{entry.vendor?.name ?? '—'}</td>
                      <td className="wrap">{entry.description || '—'}</td>
                      <td>
                        {canLogTime && (
                          <IconButton
                            size="sm"
                            variant="ghost"
                            label={`Delete cost of ${formatMoney(entry.amount)}`}
                            loading={deleteCost.isPending && deleteCost.variables === entry.id}
                            onClick={async () => {
                              try {
                                await deleteCost.mutateAsync(entry.id)
                                toast.success('Cost entry deleted')
                              } catch (error) {
                                toast.error('Could not delete the cost entry', errorMessage(error))
                              }
                            }}
                          >
                            <Trash2 size={14} />
                          </IconButton>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td className={styles.numeric}>{formatMoney(totalCost)}</td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>

        <CommentsCard workOrder={wo} />
        <FilesCard workOrder={wo} />

        <Card title="Activity">
          <ActivityTimeline items={timeline} />
          {comments.data && comments.data.items.length > 0 && (
            <p className={styles.muted} style={{ marginTop: 'var(--space-3)' }}>
              {comments.data.items.length} {comments.data.items.length === 1 ? 'comment' : 'comments'} on this work order.
            </p>
          )}
        </Card>
      </Stack>

      <CompleteDialog workOrder={wo} open={dialog === 'complete'} onClose={() => setDialog(null)} onCompleted={onCompleted} />
      <CancelDialog workOrder={wo} open={dialog === 'cancel'} onClose={() => setDialog(null)} />
      <AssigneesDialog workOrder={wo} open={dialog === 'assignees'} onClose={() => setDialog(null)} />
      <WatchersDialog workOrder={wo} open={dialog === 'watchers'} onClose={() => setDialog(null)} />
      <DependencyDialog workOrder={wo} open={dialog === 'dependency'} onClose={() => setDialog(null)} />
      <LogTimeDialog workOrder={wo} open={dialog === 'time'} onClose={() => setDialog(null)} />
      <AddCostDialog workOrder={wo} open={dialog === 'cost'} onClose={() => setDialog(null)} />
    </DetailPanel>
  )
}
