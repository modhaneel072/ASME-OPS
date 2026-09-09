import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { ChevronRight, Lock } from 'lucide-react'
import { useMemo } from 'react'
import { WORK_TYPE_LABELS, type WorkType } from '@/api/contracts/common'
import type { WorkOrder, WorkOrderSort } from '@/api/contracts/work-orders'
import { cn } from '@/lib/cn'
import { dueState, formatDate, formatDue, formatRelative } from '@/lib/dates'
import { AvatarStack, DataTable, ListRow, PriorityBadge, StatusBadge } from '@/ui'
import styles from './work-orders.module.css'
import { NARROW_QUERY, useMediaQuery } from './useMediaQuery'

export function workTypeLabel(value: string): string {
  return WORK_TYPE_LABELS[value as WorkType] ?? value
}

const CLOSED = new Set(['done', 'canceled', 'skipped'])

/** Due text with the overdue/today state baked in, so colour is never the only signal. */
export function DueLabel({ workOrder, compact }: { workOrder: WorkOrder; compact?: boolean }) {
  if (CLOSED.has(workOrder.status)) {
    if (workOrder.status === 'done') return <span className={styles.due}>{compact ? formatDate(workOrder.completed_at) : `Completed ${formatDate(workOrder.completed_at)}`}</span>
    return <span className={styles.due}>{formatDate(workOrder.canceled_at) === '—' ? 'No due date' : `Canceled ${formatDate(workOrder.canceled_at)}`}</span>
  }
  const state = workOrder.is_overdue ? 'overdue' : dueState(workOrder.due_at)
  if (!workOrder.due_at) return <span className={cn(styles.due, styles.muted)}>No due date</span>
  return (
    <span className={cn(styles.due, state === 'overdue' && styles.due_overdue, state === 'today' && styles.due_today)}>
      {state === 'overdue' && !/overdue|yesterday/.test(formatDue(workOrder.due_at)) ? `Overdue · ${formatDue(workOrder.due_at)}` : formatDue(workOrder.due_at)}
    </span>
  )
}

export interface WorkOrderPanelListProps {
  items: WorkOrder[]
  selectedId?: string | null
  cursorId?: string | null
  rowLink: (workOrder: WorkOrder) => string
}

export function WorkOrderPanelList({ items, selectedId, cursorId, rowLink }: WorkOrderPanelListProps) {
  const narrow = useMediaQuery(NARROW_QUERY)
  return (
    <ul aria-label="Work orders">
      {items.map((wo) => (
        <li key={wo.id} data-work-order-id={wo.id}>
          <ListRow
            to={rowLink(wo)}
            selected={wo.id === selectedId}
            className={cn(cursorId === wo.id && styles.cursorRow)}
            leading={<span className={styles.number}>#{wo.number}</span>}
            title={
              <span className={styles.rowTitle}>
                <span className={styles.rowTitleText}>{wo.title}</span>
                {wo.is_blocked && (
                  <span className={styles.lock} title="Blocked by dependencies" role="img" aria-label="Blocked by dependencies">
                    <Lock size={14} aria-hidden="true" />
                  </span>
                )}
              </span>
            }
            meta={
              <>
                <PriorityBadge priority={wo.priority} showLabel={!narrow} />
                <DueLabel workOrder={wo} compact />
                {wo.assignees.length > 0 && <AvatarStack people={wo.assignees} />}
                {wo.assignee_teams.map((team) => (
                  <span key={team.id} className={styles.teamChip}>
                    {team.name}
                  </span>
                ))}
                {wo.project && <span className={styles.projectCode}>{wo.project.code}</span>}
                {wo.sub_work_orders.total > 0 && (
                  <span className={styles.subCount} title="Sub-work orders done">
                    {wo.sub_work_orders.done}/{wo.sub_work_orders.total}
                  </span>
                )}
              </>
            }
            trailing={
              <span className={styles.rowTrailing}>
                <StatusBadge status={wo.status} size="sm" />
                <ChevronRight size={16} style={{ color: 'var(--color-text-disabled)' }} aria-hidden="true" />
              </span>
            }
            data-testid="work-order-row"
          />
        </li>
      ))}
    </ul>
  )
}

export interface WorkOrderTableProps {
  items: WorkOrder[]
  selectedId?: string | null
  sort: WorkOrderSort
  onSortChange: (sort: WorkOrderSort) => void
  onOpen: (workOrder: WorkOrder) => void
}

const SORTABLE: Record<string, string> = { number: 'number', title: 'title', priority: 'priority', due_at: 'due_at', updated_at: 'updated_at' }

export function sortToSorting(sort: string): SortingState {
  const desc = sort.startsWith('-')
  const key = desc ? sort.slice(1) : sort
  return SORTABLE[key] ? [{ id: key, desc }] : []
}

export function WorkOrderTable({ items, selectedId, sort, onSortChange, onOpen }: WorkOrderTableProps) {
  const columns = useMemo<ColumnDef<WorkOrder, unknown>[]>(
    () => [
      { id: 'number', header: 'Number', accessorKey: 'number', cell: ({ row }) => <span className="mono">#{row.original.number}</span>, meta: { width: 90 } },
      { id: 'title', header: 'Title', accessorKey: 'title', cell: ({ row }) => <span className={styles.cellTitle}>{row.original.title}</span> },
      { id: 'status', header: 'Status', enableSorting: false, cell: ({ row }) => <StatusBadge status={row.original.status} size="sm" /> },
      { id: 'priority', header: 'Priority', accessorKey: 'priority', cell: ({ row }) => <PriorityBadge priority={row.original.priority} /> },
      {
        id: 'assignees',
        header: 'Assignees',
        enableSorting: false,
        cell: ({ row }) =>
          row.original.assignees.length || row.original.assignee_teams.length ? (
            <span className={styles.badges}>
              {row.original.assignees.length > 0 && <AvatarStack people={row.original.assignees} />}
              {row.original.assignee_teams.map((team) => (
                <span key={team.id} className={styles.teamChip}>
                  {team.name}
                </span>
              ))}
            </span>
          ) : (
            <span className={styles.muted}>Unassigned</span>
          ),
      },
      { id: 'due_at', header: 'Due', accessorKey: 'due_at', cell: ({ row }) => <DueLabel workOrder={row.original} compact /> },
      { id: 'project', header: 'Project', enableSorting: false, cell: ({ row }) => row.original.project?.code ?? '—' },
      { id: 'location', header: 'Location', enableSorting: false, cell: ({ row }) => row.original.location?.name ?? '—' },
      { id: 'updated_at', header: 'Updated', accessorKey: 'updated_at', cell: ({ row }) => formatRelative(row.original.updated_at) },
    ],
    [],
  )
  const sorting = sortToSorting(sort)
  return (
    <div className={styles.tableWrap}>
      <DataTable<WorkOrder>
        columns={columns}
        data={items}
        getRowId={(row) => row.id}
        sorting={sorting}
        onSortingChange={(updater) => {
          const next = typeof updater === 'function' ? updater(sorting) : updater
          const first = next[0]
          if (!first) onSortChange('-updated_at')
          else onSortChange(`${first.desc ? '-' : ''}${first.id}` as WorkOrderSort)
        }}
        onRowClick={onOpen}
        selectedId={selectedId ?? null}
        rowLabel={(row) => `#${row.number} ${row.title}`}
      />
    </div>
  )
}
