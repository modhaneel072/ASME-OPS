import { AlertTriangle } from 'lucide-react'
import { formatQuantity, stockStateLabel, type StockState } from '@/api/contracts/parts'
import { Badge, type BadgeTone } from '@/ui'
import styles from './parts.module.css'

const STOCK_TONES: Record<StockState, BadgeTone> = {
  ok: 'success',
  low: 'warning',
  out: 'danger',
  untracked: 'neutral',
}

/** Stock state as a dotted chip: colour is never the only signal, the label carries it. */
export function StockChip({ state, size }: { state: string | null | undefined; size?: 'sm' }) {
  const tone = STOCK_TONES[(state ?? 'untracked') as StockState] ?? 'neutral'
  return (
    <Badge tone={tone} size={size} dot>
      {stockStateLabel(state)}
    </Badge>
  )
}

export function CriticalBadge({ size }: { size?: 'sm' }) {
  return (
    <Badge tone="danger" size={size} title="Critical part: low stock escalates to the configured team">
      <AlertTriangle size={12} aria-hidden="true" />
      Critical
    </Badge>
  )
}

/** Available quantity plus its unit, with the number in tabular figures. */
export function QuantityText({ value, unit }: { value: number | null | undefined; unit?: string | null }) {
  return (
    <span className={styles.quantity}>
      <span className={styles.quantityValue}>{formatQuantity(value)}</span>
      {unit && <span className={styles.quantityUnit}>{unit}</span>}
    </span>
  )
}

/** A signed ledger delta: `+4` / `−4`, never a bare minus glyph. */
export function DeltaText({ value }: { value: number }) {
  if (value === 0) return <span className={styles.deltaZero}>0</span>
  const positive = value > 0
  return (
    <span className={positive ? styles.deltaUp : styles.deltaDown}>
      {positive ? '+' : '−'}
      {formatQuantity(Math.abs(value))}
    </span>
  )
}
