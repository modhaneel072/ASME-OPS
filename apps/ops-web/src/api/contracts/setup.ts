import { z } from 'zod'

/**
 * Setup Center payload (`GET /setup` and every `POST /setup/*` action return
 * the same shape). Progress is derived on the server from live data; nothing
 * here is stored client-side. See `asme/ops/services/setup_center.py`.
 */

export const SETUP_TASK_STATUSES = ['complete', 'incomplete', 'unavailable'] as const
export const SetupTaskStatus = z.enum(SETUP_TASK_STATUSES)
export type SetupTaskStatus = z.infer<typeof SetupTaskStatus>

export const SetupTask = z.object({
  key: z.string(),
  title: z.string(),
  description: z.string(),
  estimated_minutes: z.number(),
  status: SetupTaskStatus,
  /** Build stage in which an `unavailable` task ships; null when the task is live. */
  stage: z.number().nullable(),
  /** Absolute app path, e.g. `/app/locations`. */
  href: z.string(),
  /** Live count backing the check (assets registered, active members, …) or null. */
  count: z.number().nullable(),
  /** Optional tasks never count toward the percentage. */
  optional: z.boolean(),
})
export type SetupTask = z.infer<typeof SetupTask>

export const SetupPhase = z.object({
  key: z.string(),
  title: z.string(),
  description: z.string(),
  tasks: z.array(SetupTask),
})
export type SetupPhase = z.infer<typeof SetupPhase>

export const SetupProgressSummary = z.object({
  completed: z.number(),
  available: z.number(),
  percent: z.number(),
})
export type SetupProgressSummary = z.infer<typeof SetupProgressSummary>

export const SetupProgress = z.object({
  phases: z.array(SetupPhase),
  progress: SetupProgressSummary,
  /** Per-user preference; the shell banner hides while true. */
  banner_dismissed: z.boolean(),
  /** Chapter-wide timestamp set by `POST /setup/complete`; null until then. */
  completed_at: z.string().nullable(),
})
export type SetupProgress = z.infer<typeof SetupProgress>

/** Task keys the server emits today; the UI falls back gracefully for unknown ones. */
export const SETUP_TASK_KEYS = [
  'chapter_profile',
  'locations',
  'assets',
  'teams_users',
  'officer_guide',
  'first_project',
  'categories',
  'parts',
  'procedure',
  'maintenance_plan',
  'request_portal',
  'automation',
  'dashboard',
] as const
export type SetupTaskKey = (typeof SETUP_TASK_KEYS)[number]

export const OFFICER_GUIDE_TASK_KEY: SetupTaskKey = 'officer_guide'

/** Flattens every task across phases, preserving server order. */
export function allSetupTasks(progress: Pick<SetupProgress, 'phases'>): SetupTask[] {
  return progress.phases.flatMap((phase) => phase.tasks)
}

/** Looks up one task by key. */
export function findSetupTask(progress: Pick<SetupProgress, 'phases'>, key: string): SetupTask | undefined {
  return allSetupTasks(progress).find((task) => task.key === key)
}

/**
 * The task to surface as "up next": the first incomplete required task, then
 * the first incomplete optional one. Unavailable tasks are never suggested.
 */
export function nextSetupTask(progress: Pick<SetupProgress, 'phases'>): SetupTask | null {
  const tasks = allSetupTasks(progress)
  const incomplete = tasks.filter((task) => task.status === 'incomplete')
  return incomplete.find((task) => !task.optional) ?? incomplete[0] ?? null
}

export interface SetupPhaseSummary {
  /** Required tasks that can be completed in this stage. */
  available: number
  completed: number
  /** True when every task in the phase belongs to a later stage. */
  deferred: boolean
}

export function summarizeSetupPhase(phase: Pick<SetupPhase, 'tasks'>): SetupPhaseSummary {
  const countable = phase.tasks.filter((task) => task.status !== 'unavailable' && !task.optional)
  return {
    available: countable.length,
    completed: countable.filter((task) => task.status === 'complete').length,
    deferred: phase.tasks.length > 0 && phase.tasks.every((task) => task.status === 'unavailable'),
  }
}
