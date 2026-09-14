import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/cn'
import styles from './feedback.module.css'

/* Skeleton ------------------------------------------------------------------ */

export function Skeleton({ width, height = 14, circle, className, style }: { width?: number | string; height?: number | string; circle?: boolean; className?: string; style?: CSSProperties }) {
  return <span aria-hidden="true" className={cn(styles.skeleton, circle && styles.skeleton_circle, className)} style={{ width: width ?? '100%', height, ...style }} />
}

export function SkeletonRows({ rows = 6, avatar = false }: { rows?: number; avatar?: boolean }) {
  return (
    <div className={styles.skeletonRows} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className={styles.skeletonRow}>
          {avatar && <Skeleton width={28} height={28} circle />}
          <div style={{ flex: 1, display: 'grid', gap: 6 }}>
            <Skeleton width={`${55 + ((index * 17) % 30)}%`} />
            <Skeleton width={`${30 + ((index * 23) % 25)}%`} height={10} />
          </div>
          <Skeleton width={64} height={18} />
        </div>
      ))}
    </div>
  )
}

export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div style={{ display: 'grid', gap: 8 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton key={index} width={`${90 - ((index * 13) % 40)}%`} />
      ))}
    </div>
  )
}

/* Empty state --------------------------------------------------------------- */

type Illustration = 'clipboard' | 'folder' | 'box' | 'pin' | 'users' | 'tag' | 'search' | 'chart' | 'bell' | 'inbox'

function EmptyIllustration({ kind }: { kind: Illustration }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  switch (kind) {
    case 'clipboard':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <rect x="22" y="16" width="52" height="66" rx="6" />
          <path d="M36 16v-4a4 4 0 0 1 4-4h16a4 4 0 0 1 4 4v4" />
          <path d="M34 42l6 6 12-12M34 62h28" />
        </svg>
      )
    case 'folder':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M12 30a6 6 0 0 1 6-6h20l8 8h32a6 6 0 0 1 6 6v34a6 6 0 0 1-6 6H18a6 6 0 0 1-6-6z" />
          <path d="M12 44h72" />
        </svg>
      )
    case 'box':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M16 34l32-16 32 16v30L48 80 16 64z" />
          <path d="M16 34l32 16 32-16M48 50v30" />
        </svg>
      )
    case 'pin':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M48 84s-26-24-26-44a26 26 0 0 1 52 0c0 20-26 44-26 44z" />
          <circle cx="48" cy="40" r="9" />
        </svg>
      )
    case 'users':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <circle cx="36" cy="34" r="12" />
          <circle cx="64" cy="40" r="9" />
          <path d="M12 78c0-14 10-22 24-22s24 8 24 22M60 60c12 0 22 6 22 18" />
        </svg>
      )
    case 'tag':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M14 18h30l38 38-30 30-38-38z" />
          <circle cx="30" cy="34" r="5" />
        </svg>
      )
    case 'search':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <circle cx="42" cy="42" r="24" />
          <path d="M60 60l22 22" />
        </svg>
      )
    case 'chart':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M14 82h68M24 70V46M42 70V30M60 70V52M78 70V22" />
        </svg>
      )
    case 'bell':
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M26 64V44a22 22 0 0 1 44 0v20l6 8H20zM40 78a8 8 0 0 0 16 0" />
        </svg>
      )
    case 'inbox':
    default:
      return (
        <svg viewBox="0 0 96 96" className={styles.emptyIllustration} aria-hidden="true" {...common}>
          <path d="M16 54l10-30h44l10 30v20a6 6 0 0 1-6 6H22a6 6 0 0 1-6-6z" />
          <path d="M16 54h20l4 8h16l4-8h20" />
        </svg>
      )
  }
}

export interface EmptyStateProps {
  title: string
  description?: ReactNode
  action?: ReactNode
  illustration?: Illustration
  compact?: boolean
  className?: string
}

export function EmptyState({ title, description, action, illustration = 'clipboard', compact, className }: EmptyStateProps) {
  return (
    <div className={cn(styles.empty, compact && styles.empty_compact, className)} role="status">
      <EmptyIllustration kind={illustration} />
      <p className={styles.emptyTitle}>{title}</p>
      {description && <p className={styles.emptyDescription}>{description}</p>}
      {action && <div className={styles.emptyAction}>{action}</div>}
    </div>
  )
}

/* Inline alert -------------------------------------------------------------- */

export type AlertTone = 'info' | 'success' | 'warning' | 'danger'

const ALERT_ICONS = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle }

export function InlineAlert({ tone = 'info', title, children, actions, className }: { tone?: AlertTone; title?: ReactNode; children?: ReactNode; actions?: ReactNode; className?: string }) {
  const Icon = ALERT_ICONS[tone]
  return (
    <div className={cn(styles.alert, styles[`alert_${tone}`], className)} role={tone === 'danger' || tone === 'warning' ? 'alert' : 'status'}>
      <Icon className={styles.alertIcon} size={18} aria-hidden="true" />
      <div className={styles.alertBody}>
        {title && <p className={styles.alertTitle}>{title}</p>}
        {children && <div>{children}</div>}
        {actions && <div className={styles.alertActions}>{actions}</div>}
      </div>
    </div>
  )
}

/* Progress ------------------------------------------------------------------ */

export function ProgressBar({ value, label, tone, showValue = true }: { value: number; label?: string; tone?: 'gold' | 'success' | 'danger'; showValue?: boolean }) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)))
  return (
    <div>
      {(label || showValue) && (
        <div className={styles.progressLabel}>
          <span>{label}</span>
          {showValue && <span className="mono">{clamped}%</span>}
        </div>
      )}
      <div className={cn(styles.progress, tone && styles[`progress_${tone}`])} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={clamped} aria-label={label}>
        <div className={styles.progressBar} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  )
}

export function ProgressRing({ value, size = 64, stroke = 6, label }: { value: number; size?: number; stroke?: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)))
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  return (
    <div className={styles.ring} style={{ width: size, height: size }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={clamped} aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--color-bg-subtle)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-primary)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className={styles.ringValue}>{clamped}%</span>
    </div>
  )
}
