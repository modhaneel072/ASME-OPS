import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import type { Part, PartSort } from '@/api/contracts/parts'
import { Checkbox } from '@/ui'
import { CriticalBadge, QuantityText, StockChip } from './bits'
import { nextSort, sortDirection } from './params'
import styles from './parts.module.css'

export interface PartsTableProps {
  rows: Part[]
  sort: PartSort
  onSortChange: (sort: PartSort) => void
  onOpen: (part: Part) => void
  selectedId?: string
  /** The Low stock tab lets rows be picked for a purchase request. */
  selectable?: boolean
  checked?: Set<string>
  onToggle?: (id: string, checked: boolean) => void
  onToggleAll?: (checked: boolean) => void
}

/**
 * The parts list. A real table, because the columns (available, on hand, stock
 * state) are compared down the column far more often than they are read across
 * the row.
 */
export function PartsTable({ rows, sort, onSortChange, onOpen, selectedId, selectable, checked, onToggle, onToggleAll }: PartsTableProps) {
  const allChecked = selectable && rows.length > 0 && rows.every((row) => checked?.has(row.id))

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <caption className="sr-only">Parts with their available stock, on-hand quantity, storage location and preferred vendor</caption>
        <thead>
          <tr>
            {selectable && (
              <th scope="col" className={styles.selectCell}>
                <Checkbox label={<span className="sr-only">Select every part on this page</span>} checked={Boolean(allChecked)} onChange={(value) => onToggleAll?.(value)} />
              </th>
            )}
            <SortableHeader label="Part" column="name" sort={sort} onSortChange={onSortChange} />
            <SortableHeader label="Available" column="available" sort={sort} onSortChange={onSortChange} numeric />
            <th scope="col" className={`${styles.numeric} ${styles.hideNarrow}`}>
              On hand
            </th>
            <th scope="col" className={styles.hideNarrow}>
              Stored at
            </th>
            <th scope="col" className={styles.hideNarrow}>
              Preferred vendor
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((part) => (
            <tr
              key={part.id}
              data-testid="part-row"
              aria-selected={part.id === selectedId || undefined}
              tabIndex={0}
              aria-label={part.name}
              onClick={(event) => {
                // The selection checkbox is inside the row; ticking it must not also open the part.
                if ((event.target as HTMLElement).closest('label')) return
                onOpen(part)
              }}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onOpen(part)
                }
              }}
            >
              {selectable && (
                <td className={styles.selectCell}>
                  <Checkbox label={<span className="sr-only">{`Select ${part.name}`}</span>} checked={Boolean(checked?.has(part.id))} onChange={(value) => onToggle?.(part.id, value)} />
                </td>
              )}
              <td>
                <span className={styles.nameCell}>
                  <span className={styles.nameText}>
                    {part.name}
                    {part.is_critical && <CriticalBadge size="sm" />}
                    {part.is_active === false && <span className={styles.cellMuted}>(retired)</span>}
                  </span>
                  <span className={styles.code}>{part.sku || 'No SKU'}</span>
                </span>
              </td>
              <td className={styles.numeric}>
                <span className={styles.availableCell}>
                  <QuantityText value={part.totals.available} unit={part.unit} />
                  <StockChip state={part.stock_state} size="sm" />
                </span>
              </td>
              <td className={`${styles.numeric} ${styles.hideNarrow}`}>
                <QuantityText value={part.totals.on_hand} />
              </td>
              <td className={`${styles.cellMuted} ${styles.hideNarrow}`}>{part.default_location?.name ?? '—'}</td>
              <td className={`${styles.cellMuted} ${styles.hideNarrow}`}>{part.preferred_vendor?.name ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SortableHeader({
  label,
  column,
  sort,
  onSortChange,
  numeric,
}: {
  label: string
  column: 'name' | 'available'
  sort: PartSort
  onSortChange: (sort: PartSort) => void
  numeric?: boolean
}) {
  const direction = sortDirection(sort, column)
  return (
    <th scope="col" aria-sort={direction ?? 'none'} className={numeric ? styles.numeric : undefined}>
      <button type="button" className={styles.sortButton} onClick={() => onSortChange(nextSort(sort, column))}>
        {label}
        {direction === 'ascending' ? (
          <ArrowUp size={12} aria-hidden="true" />
        ) : direction === 'descending' ? (
          <ArrowDown size={12} aria-hidden="true" />
        ) : (
          <ArrowUpDown size={12} aria-hidden="true" style={{ opacity: 0.5 }} />
        )}
      </button>
    </th>
  )
}
