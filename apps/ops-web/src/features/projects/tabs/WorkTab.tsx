import type { ColumnDef } from '@tanstack/react-table'
import { ExternalLink, Plus } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Project, ProjectWorkOrderRow } from '@/api/contracts/projects'
import { useProjectWorkOrders } from '@/api/queries/projects'
import { dueState, formatDue } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import { AvatarStack, DataTable, EmptyState, LinkButton, PriorityBadge, StatusBadge } from '@/ui'
import { newWorkOrderHref, QueryState, workOrdersHref } from '../shared'
import styles from '../projects.module.css'

export function WorkTab({ project }: { project: Project }) {
  const list = useProjectWorkOrders(project.id)
  const navigate = useNavigate()
  const can = useCan()
  const canCreate = can('work_order.create')

  const columns = useMemo<ColumnDef<ProjectWorkOrderRow, unknown>[]>(
    () => [
      { id: 'number', header: '#', accessorKey: 'number', cell: ({ row }) => <span className="mono">#{row.original.number}</span>, meta: { width: 72 } },
      { id: 'title', header: 'Title', accessorKey: 'title', meta: { wrap: true } },
      { id: 'status', header: 'Status', cell: ({ row }) => <StatusBadge status={row.original.status} size="sm" /> },
      { id: 'priority', header: 'Priority', cell: ({ row }) => <PriorityBadge priority={row.original.priority} /> },
      { id: 'assignees', header: 'Assignees', cell: ({ row }) => (row.original.assignees.length ? <AvatarStack people={row.original.assignees} /> : <span className={styles.muted}>Unassigned</span>) },
      {
        id: 'due',
        header: 'Due',
        cell: ({ row }) => {
          const state = dueState(row.original.due_at)
          const overdue = state === 'overdue' && !['done', 'canceled', 'skipped'].includes(row.original.status)
          return <span style={overdue ? { color: 'var(--color-danger-text)', fontWeight: 600 } : undefined}>{formatDue(row.original.due_at)}</span>
        },
      },
    ],
    [],
  )

  return (
    <div>
      <div className={styles.toolbar}>
        <span className={styles.muted}>{list.data ? `${list.data.total ?? list.data.items.length} work orders` : ''}</span>
        <span className={styles.toolbarSpacer} />
        <LinkButton to={workOrdersHref(project.id)} size="sm" leadingIcon={<ExternalLink size={14} />}>
          Open in Work Orders
        </LinkButton>
        {canCreate && (
          <LinkButton to={newWorkOrderHref(project.id)} size="sm" variant="primary" leadingIcon={<Plus size={14} />}>
            New work order
          </LinkButton>
        )}
      </div>
      <QueryState isPending={list.isPending} isError={list.isError} error={list.error} onRetry={() => void list.refetch()} title="Work orders could not be loaded">
        <DataTable
          columns={columns}
          data={list.data?.items ?? []}
          getRowId={(row) => row.id}
          onRowClick={(row) => navigate(`/work-orders/${row.id}`)}
          rowLabel={(row) => `#${row.number} ${row.title}`}
          emptyState={<EmptyState compact illustration="clipboard" title="No work orders yet" description="Work orders created for this project show up here." />}
        />
      </QueryState>
    </div>
  )
}
