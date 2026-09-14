import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { useMemo, type ReactNode } from 'react'
import { ASSET_CRITICALITY_LABELS, type Asset, type AssetCriticality, type AssetSort } from '@/api/contracts/assets'
import { formatRelative } from '@/lib/dates'
import { DataTable, StatusBadge } from '@/ui'
import styles from './assets.module.css'
import { TypeChips } from './bits'

const SORT_COLUMNS: Record<string, string> = { name: 'name', status: 'status', criticality: 'criticality', updated_at: 'updated_at' }

export function sortToState(sort: AssetSort): SortingState {
  const desc = sort.startsWith('-')
  const key = desc ? sort.slice(1) : sort
  return SORT_COLUMNS[key] ? [{ id: key, desc }] : []
}

export function stateToSort(state: SortingState): AssetSort {
  const first = state[0]
  if (!first || !SORT_COLUMNS[first.id]) return 'name'
  return `${first.desc ? '-' : ''}${first.id}` as AssetSort
}

export interface AssetTableProps {
  rows: Asset[]
  sort: AssetSort
  onSortChange: (sort: AssetSort) => void
  onOpen: (asset: Asset) => void
  selectedId?: string | null
  emptyState?: ReactNode
}

export function AssetTable({ rows, sort, onSortChange, onOpen, selectedId, emptyState }: AssetTableProps) {
  const columns = useMemo<ColumnDef<Asset, unknown>[]>(
    () => [
      { id: 'name', accessorKey: 'name', header: 'Name', cell: ({ row }) => <span className={styles.cellName}>{row.original.name}</span>, meta: { wrap: true } },
      { id: 'code', accessorKey: 'code', header: 'Code', enableSorting: false, cell: ({ row }) => (row.original.code ? <span className={styles.code}>{row.original.code}</span> : <span className={styles.cellMuted}>—</span>) },
      { id: 'status', accessorKey: 'status', header: 'Status', cell: ({ row }) => <StatusBadge status={row.original.status} size="sm" /> },
      {
        id: 'criticality',
        accessorKey: 'criticality',
        header: 'Criticality',
        cell: ({ row }) => {
          const value = (row.original.criticality ?? 'none') as AssetCriticality
          return value === 'none' ? <span className={styles.cellMuted}>—</span> : ASSET_CRITICALITY_LABELS[value]
        },
      },
      { id: 'types', header: 'Types', enableSorting: false, cell: ({ row }) => (row.original.types.length ? <TypeChips types={row.original.types} max={2} /> : <span className={styles.cellMuted}>—</span>) },
      { id: 'location', header: 'Location', enableSorting: false, cell: ({ row }) => row.original.location?.name ?? <span className={styles.cellMuted}>—</span> },
      { id: 'project', header: 'Project', enableSorting: false, cell: ({ row }) => row.original.project?.name ?? <span className={styles.cellMuted}>—</span> },
      { id: 'team', header: 'Team', enableSorting: false, cell: ({ row }) => row.original.team?.name ?? <span className={styles.cellMuted}>—</span> },
      { id: 'open_work', header: 'Open work', enableSorting: false, cell: ({ row }) => row.original.open_work_order_count ?? 0, meta: { numeric: true } },
      { id: 'updated_at', accessorKey: 'updated_at', header: 'Updated', cell: ({ row }) => <span className={styles.cellMuted}>{formatRelative(row.original.updated_at)}</span> },
    ],
    [],
  )

  const sorting = useMemo(() => sortToState(sort), [sort])

  return (
    <DataTable<Asset>
      columns={columns}
      data={rows}
      getRowId={(row) => row.id}
      sorting={sorting}
      onSortingChange={(updater) => {
        const next = typeof updater === 'function' ? updater(sorting) : updater
        onSortChange(stateToSort(next))
      }}
      onRowClick={onOpen}
      selectedId={selectedId}
      rowLabel={(row) => `Open ${row.name}`}
      emptyState={emptyState}
    />
  )
}
