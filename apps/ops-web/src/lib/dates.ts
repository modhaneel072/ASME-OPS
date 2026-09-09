import { differenceInCalendarDays, format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns'

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const parsed = parseISO(value)
  return isValid(parsed) ? parsed : null
}

export function formatDate(value: string | null | undefined, pattern = 'MMM d, yyyy'): string {
  const date = parseDate(value)
  return date ? format(date, pattern) : '—'
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseDate(value)
  return date ? format(date, 'MMM d, yyyy · h:mm a') : '—'
}

export function formatRelative(value: string | null | undefined): string {
  const date = parseDate(value)
  if (!date) return '—'
  return formatDistanceToNowStrict(date, { addSuffix: true })
}

export type DueState = 'none' | 'overdue' | 'today' | 'soon' | 'later'

export function dueState(value: string | null | undefined, now = new Date()): DueState {
  const date = parseDate(value)
  if (!date) return 'none'
  const days = differenceInCalendarDays(date, now)
  if (date < now && days < 0) return 'overdue'
  if (days === 0) return date < now ? 'overdue' : 'today'
  if (days <= 3) return 'soon'
  return 'later'
}

export function formatDue(value: string | null | undefined, now = new Date()): string {
  const date = parseDate(value)
  if (!date) return 'No due date'
  const days = differenceInCalendarDays(date, now)
  if (days === 0) return `Due today, ${format(date, 'h:mm a')}`
  if (days === 1) return 'Due tomorrow'
  if (days === -1) return 'Due yesterday'
  if (days < 0) return `${Math.abs(days)} days overdue`
  if (days <= 7) return `Due in ${days} days`
  return `Due ${format(date, 'MMM d')}`
}

export function formatMinutes(minutes: number | null | undefined): string {
  if (!minutes) return '0m'
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest}m`
  if (rest === 0) return `${hours}h`
  return `${hours}h ${rest}m`
}

export function toDateTimeLocal(value: string | null | undefined): string {
  const date = parseDate(value)
  return date ? format(date, "yyyy-MM-dd'T'HH:mm") : ''
}

export function fromDateTimeLocal(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  return isValid(date) ? date.toISOString() : null
}

export function formatMoney(value: number | null | undefined, currency = 'USD'): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}
