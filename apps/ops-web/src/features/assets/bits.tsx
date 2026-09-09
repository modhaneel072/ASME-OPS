import { ASSET_CRITICALITY_LABELS, type AssetCriticality, type AssetTypeBrief } from '@/api/contracts/assets'
import { labelFor } from '@/api/contracts/common'
import { Badge } from '@/ui'
import styles from './assets.module.css'

export function TypeChips({ types, max = 3 }: { types: AssetTypeBrief[]; max?: number }) {
  if (!types.length) return null
  const shown = types.slice(0, max)
  const rest = types.length - shown.length
  return (
    <span className={styles.chips} aria-label={`Types: ${types.map((t) => t.name).join(', ')}`}>
      {shown.map((type) => (
        <span key={type.id} className={styles.typeChip}>
          <span className={styles.typeDot} style={type.color ? { background: type.color } : undefined} aria-hidden="true" />
          {type.name}
        </span>
      ))}
      {rest > 0 && <span className={styles.typeChip}>+{rest}</span>}
    </span>
  )
}

/** Colour dot plus text, so status is never conveyed by colour alone. */
export function StatusText({ status }: { status: string }) {
  return (
    <span className={styles.statusText}>
      <span className={styles.statusDot} data-status={status} aria-hidden="true" />
      {labelFor(status)}
    </span>
  )
}

const CRITICALITY_TONES: Record<AssetCriticality, 'neutral' | 'success' | 'warning' | 'danger'> = { none: 'neutral', low: 'success', medium: 'warning', high: 'danger' }

/** Criticality badge; "none" renders nothing in lists (the detail spells it out). */
export function CriticalityBadge({ criticality, size, showNone }: { criticality: string | undefined; size?: 'sm'; showNone?: boolean }) {
  const value = (criticality ?? 'none') as AssetCriticality
  if (value === 'none' && !showNone) return null
  const label = ASSET_CRITICALITY_LABELS[value] ?? labelFor(value)
  return (
    <Badge tone={CRITICALITY_TONES[value] ?? 'neutral'} size={size} title={`Criticality: ${label}`}>
      {value === 'none' ? 'No criticality' : `${label} criticality`}
    </Badge>
  )
}
