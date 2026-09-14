import { z } from 'zod'
import { TeamRef, UserRef } from './common'

/* Date ranges (mirror asme/ops/services/dashboard.py) ------------------------ */

export const RANGE_KEYS = ['7d', '30d', '90d', 'semester', 'custom'] as const
export type RangeKey = (typeof RANGE_KEYS)[number]
export const DEFAULT_RANGE: RangeKey = '30d'
/** Longest custom window the API accepts, inclusive of both end dates. */
export const MAX_CUSTOM_DAYS = 366

export const RANGE_LABELS: Record<RangeKey, string> = {
  '7d': '7 days',
  '30d': '30 days',
  '90d': '90 days',
  semester: 'Semester',
  custom: 'Custom',
}

export function isRangeKey(value: string | null | undefined): value is RangeKey {
  return Boolean(value) && (RANGE_KEYS as readonly string[]).includes(value as string)
}

/* Payload (GET /reports/operations) ----------------------------------------- */

export const WeekBucket = z.object({ week_start: z.string(), created: z.number(), completed: z.number() })
export type WeekBucket = z.infer<typeof WeekBucket>

export const WorkTypeCount = z.object({ work_type: z.string(), count: z.number() })
export const StatusCount = z.object({ status: z.string(), count: z.number() })
export const PriorityCount = z.object({ priority: z.string(), count: z.number() })

export const TeamWorkload = z.object({ team: TeamRef.nullable(), open: z.number(), in_progress: z.number() })
export type TeamWorkload = z.infer<typeof TeamWorkload>

export const UserWorkload = z.object({ user: UserRef, open: z.number(), in_progress: z.number() })
export type UserWorkload = z.infer<typeof UserWorkload>

export const OperationsReport = z.object({
  range: z.object({ key: z.string(), start: z.string(), end: z.string(), timezone: z.string() }),
  created_vs_completed: z.array(WeekBucket),
  by_work_type: z.array(WorkTypeCount),
  repeating_vs_non: z.object({ repeating: z.number(), non_repeating: z.number() }),
  status_distribution: z.array(StatusCount),
  priority_distribution: z.array(PriorityCount),
  /** Fraction 0–1, or null when nothing with a due date was completed. */
  on_time_completion_rate: z.number().nullable(),
  overdue_open: z.number(),
  /** Mean hours from creation to completion, or null when nothing was completed. */
  avg_completion_hours: z.number().nullable(),
  workload_by_team: z.array(TeamWorkload),
  workload_by_user: z.array(UserWorkload),
  hours_logged: z.number(),
  parts_cost: z.number(),
  other_cost: z.number(),
  totals: z.object({ created: z.number(), completed: z.number(), open: z.number() }),
})
export type OperationsReport = z.infer<typeof OperationsReport>

/** Query parameters accepted by the endpoint; `start`/`end` only matter for `custom`. */
export interface OperationsReportParams {
  range: RangeKey
  start?: string
  end?: string
  project?: string
  team?: string
}

/* Custom range form ---------------------------------------------------------- */

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export function isIsoDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

function dayNumber(value: string): number {
  const [year, month, day] = value.split('-').map(Number)
  return Date.UTC(year, month - 1, day) / 86_400_000
}

/** Inclusive number of days covered by `start … end`; negative when reversed. */
export function customRangeDays(start: string, end: string): number {
  return dayNumber(end) - dayNumber(start) + 1
}

export const CustomRangeInput = z
  .object({
    start: z.string().refine(isIsoDate, 'Enter a start date.'),
    end: z.string().refine(isIsoDate, 'Enter an end date.'),
  })
  .superRefine((value, ctx) => {
    if (!isIsoDate(value.start) || !isIsoDate(value.end)) return
    const days = customRangeDays(value.start, value.end)
    if (days < 1) ctx.addIssue({ code: 'custom', path: ['end'], message: 'End must be on or after start.' })
    else if (days > MAX_CUSTOM_DAYS) ctx.addIssue({ code: 'custom', path: ['end'], message: `Custom ranges may cover at most ${MAX_CUSTOM_DAYS} days.` })
  })
export type CustomRangeInput = z.infer<typeof CustomRangeInput>
