/** Small shared pieces of the purchase-request screens. */

import { AlertTriangle } from 'lucide-react'
import { PURCHASE_REQUEST_STATUS_LABELS, purchaseRequestStatusLabel, type PurchaseRequestStatus } from '@/api/contracts/purchaseRequests'
import { formatDate, formatMoney } from '@/lib/dates'
import { Badge, type BadgeTone } from '@/ui'
import styles from './purchase-requests.module.css'

const STATUS_TONES: Record<PurchaseRequestStatus, BadgeTone> = {
  draft: 'outline',
  submitted: 'info',
  treasurer_review: 'info',
  advisor_review: 'warning',
  approved: 'success',
  ordered: 'purple',
  partially_received: 'warning',
  received: 'success',
  declined: 'danger',
  canceled: 'neutral',
}

export function PurchaseRequestStatusBadge({ status, size }: { status: string | null | undefined; size?: 'sm' }) {
  const tone = (status && STATUS_TONES[status as PurchaseRequestStatus]) || 'neutral'
  return (
    <Badge tone={tone} dot size={size}>
      {purchaseRequestStatusLabel(status)}
    </Badge>
  )
}

export function statusLabel(status: string | null | undefined): string {
  return purchaseRequestStatusLabel(status)
}

export { PURCHASE_REQUEST_STATUS_LABELS }

/** Needed-by date; overdue requests get a danger treatment and a spoken hint. */
export function NeededBy({ date, overdue }: { date: string | null | undefined; overdue: boolean }) {
  if (!date) return <span className={styles.muted}>No date</span>
  if (!overdue) return <span>{formatDate(date)}</span>
  return (
    <span className={styles.overdue}>
      <AlertTriangle size={13} aria-hidden="true" />
      {formatDate(date)}
      <span className="sr-only"> (overdue)</span>
    </span>
  )
}

export function Money({ value, muted }: { value: number | null | undefined; muted?: boolean }) {
  if (value === null || value === undefined) return <span className={styles.muted}>—</span>
  return <span className={muted ? styles.muted : styles.money}>{formatMoney(value)}</span>
}

export function money(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : formatMoney(value)
}
