import { format, subDays } from 'date-fns'
import { parseDate } from '@/lib/dates'

export const DOT = '·'

export function formatPercent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—'
  return new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 1 }).format(rate)
}

export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return '—'
  return `${hours.toFixed(1)} h`
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

/** "Aug 3 – Aug 16, 2026", "Dec 20, 2025 – Jan 4, 2026" or a single day. */
export function formatRangeLabel(start: string, end: string): string {
  const from = parseDate(start)
  const to = parseDate(end)
  if (!from || !to) return `${start} – ${end}`
  if (start === end) return format(from, 'MMM d, yyyy')
  const sameYear = from.getFullYear() === to.getFullYear()
  return `${format(from, sameYear ? 'MMM d' : 'MMM d, yyyy')} – ${format(to, 'MMM d, yyyy')}`
}

export function formatWeek(weekStart: string): string {
  const date = parseDate(weekStart)
  return date ? format(date, 'MMM d') : weekStart
}

export function todayIso(): string {
  return format(new Date(), 'yyyy-MM-dd')
}

export function daysAgoIso(days: number): string {
  return format(subDays(new Date(), days), 'yyyy-MM-dd')
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${formatCount(count)} ${count === 1 ? singular : plural}`
}

/** "a", "a and b", "a, b and c". */
export function joinList(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? ''
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

export function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1).trimEnd()}…` : value
}
