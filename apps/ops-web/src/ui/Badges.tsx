import { AlertOctagon } from 'lucide-react'
import type { ReactNode } from 'react'
import { PRIORITY_LABELS, labelFor, type Priority } from '@/api/contracts/common'
import { cn } from '@/lib/cn'
import styles from './feedback.module.css'

export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'purple' | 'gold' | 'outline'

export function Badge({ tone = 'neutral', children, dot, size, className, title }: { tone?: BadgeTone; children: ReactNode; dot?: boolean; size?: 'sm'; className?: string; title?: string }) {
  return (
    <span className={cn(styles.badge, styles[`tone_${tone}`], size === 'sm' && styles.badge_sm, className)} title={title}>
      {dot && <span className={styles.badgeDot} aria-hidden="true" />}
      {children}
    </span>
  )
}

const STATUS_TONES: Record<string, BadgeTone> = {
  draft: 'outline',
  open: 'info',
  in_progress: 'purple',
  on_hold: 'warning',
  done: 'success',
  canceled: 'neutral',
  skipped: 'neutral',
  planning: 'outline',
  active: 'success',
  completed: 'success',
  archived: 'neutral',
  online: 'success',
  offline_planned: 'warning',
  offline_unplanned: 'danger',
  do_not_track: 'neutral',
  retired: 'neutral',
  planned: 'outline',
  missed: 'danger',
  invited: 'warning',
  suspended: 'danger',
  low: 'success',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
}

export function StatusBadge({ status, size, className }: { status: string | null | undefined; size?: 'sm'; className?: string }) {
  const tone = (status && STATUS_TONES[status]) || 'neutral'
  return (
    <Badge tone={tone} dot size={size} className={className}>
      {labelFor(status)}
    </Badge>
  )
}

export function PriorityBadge({ priority, showLabel = true, className }: { priority: Priority | string | null | undefined; showLabel?: boolean; className?: string }) {
  const value = (priority ?? 'none') as Priority
  const label = PRIORITY_LABELS[value] ?? labelFor(value)
  return (
    <span className={cn(styles.priority, styles[`priority_${value}`], className)} title={`Priority: ${label}`} aria-label={`Priority ${label}`}>
      {value === 'critical' ? (
        <AlertOctagon size={14} aria-hidden="true" />
      ) : (
        <span className={styles.priorityBars} aria-hidden="true">
          <span className={styles.priorityBar} />
          <span className={styles.priorityBar} />
          <span className={styles.priorityBar} />
        </span>
      )}
      {showLabel && <span>{label}</span>}
    </span>
  )
}

export function CategoryChip({ name, color, size }: { name: string; color: string; size?: 'sm' }) {
  return (
    <span className={cn(styles.badge, styles.tone_outline, size === 'sm' && styles.badge_sm)}>
      <span className={styles.badgeDot} style={{ background: color }} aria-hidden="true" />
      {name}
    </span>
  )
}
