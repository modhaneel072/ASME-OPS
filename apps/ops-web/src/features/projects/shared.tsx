import type { ReactNode } from 'react'
import type { FieldValues, Path, UseFormSetError } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import type { AuditEvent } from '@/api/contracts/common'
import { Button, InlineAlert, SkeletonBlock, type TimelineItem } from '@/ui'
import styles from './projects.module.css'

export const PROJECT_TABS = ['overview', 'work', 'milestones', 'teams', 'assets', 'documents', 'budget', 'activity'] as const
export type ProjectTab = (typeof PROJECT_TABS)[number]

export const TAB_LABELS: Record<ProjectTab, string> = {
  overview: 'Overview',
  work: 'Work',
  milestones: 'Milestones',
  teams: 'Teams',
  assets: 'Assets',
  documents: 'Documents',
  budget: 'Budget',
  activity: 'Activity',
}

export function isProjectTab(value: string | undefined): value is ProjectTab {
  return Boolean(value) && (PROJECT_TABS as readonly string[]).includes(value as string)
}

/** Links into the Work Orders screen scoped to one project. */
export function workOrdersHref(projectId: string, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ 'filter[project]': projectId, ...extra })
  return `/work-orders?${params.toString()}`
}

export function newWorkOrderHref(projectId: string): string {
  return `/work-orders/new?project=${encodeURIComponent(projectId)}`
}

/** Copies server validation errors for fields the form renders onto the form (run from an effect). */
export function applyServerErrors<T extends FieldValues>(error: unknown, setError: UseFormSetError<T>, fields: readonly string[]): void {
  if (!(error instanceof ApiError && error.isValidation)) return
  for (const [field, message] of Object.entries(error.errors)) {
    if (fields.includes(field)) setError(field as Path<T>, { type: 'server', message })
  }
}

/** Messages for server-side field errors the form has no field for; shown in an alert. Pure. */
export function unmappedServerErrors(error: unknown, fields: readonly string[]): string[] {
  if (!(error instanceof ApiError && error.isValidation)) return []
  return Object.entries(error.errors)
    .filter(([field]) => !fields.includes(field))
    .map(([field, message]) => (field === 'members' ? message : `${field}: ${message}`))
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function activityToTimeline(events: AuditEvent[]): TimelineItem[] {
  return events.map((event) => ({
    id: event.id,
    title: event.summary || event.event_type.replace(/[._]/g, ' '),
    actor: event.actor?.name ?? 'System',
    at: event.occurred_at,
  }))
}

/** Loading / error / content switch shared by the detail tabs. */
export function QueryState({
  isPending,
  isError,
  error,
  onRetry,
  title,
  children,
}: {
  isPending: boolean
  isError: boolean
  error: unknown
  onRetry: () => void
  title: string
  children: ReactNode
}) {
  if (isPending) {
    return (
      <div className={styles.padded}>
        <SkeletonBlock lines={4} />
      </div>
    )
  }
  if (isError) {
    return (
      <div className={styles.padded}>
        <InlineAlert
          tone="danger"
          title={title}
          actions={
            <Button size="sm" onClick={onRetry}>
              Retry
            </Button>
          }
        >
          {errorMessage(error)}
        </InlineAlert>
      </div>
    )
  }
  return <>{children}</>
}
