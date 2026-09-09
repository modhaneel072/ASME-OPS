import { z } from 'zod'

export const UserRef = z.object({
  id: z.number(),
  name: z.string(),
  email: z.string(),
  avatar_url: z.string().nullable().optional(),
})
export type UserRef = z.infer<typeof UserRef>

export const TeamRef = z.object({ id: z.string(), name: z.string() })
export type TeamRef = z.infer<typeof TeamRef>

export const ProjectRef = z.object({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  visibility: z.enum(['chapter', 'private']).optional(),
})
export type ProjectRef = z.infer<typeof ProjectRef>

export const LocationRef = z.object({ id: z.string(), name: z.string() })
export type LocationRef = z.infer<typeof LocationRef>

export const AssetRef = z.object({ id: z.string(), name: z.string(), code: z.string().nullable().optional(), status: z.string().optional() })
export type AssetRef = z.infer<typeof AssetRef>

export const CategoryRef = z.object({ id: z.string(), name: z.string(), color: z.string(), icon: z.string().optional() })
export type CategoryRef = z.infer<typeof CategoryRef>

export const VendorRef = z.object({ id: z.string(), name: z.string() })
export type VendorRef = z.infer<typeof VendorRef>

export const RoleRef = z.object({
  id: z.string(),
  name: z.string(),
  system_key: z.string().nullable(),
  is_custom: z.boolean().optional(),
})
export type RoleRef = z.infer<typeof RoleRef>

export const AuditEvent = z.object({
  id: z.string(),
  event_type: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  actor: UserRef.nullable(),
  summary: z.string().nullable(),
  before: z.unknown().nullable().optional(),
  after: z.unknown().nullable().optional(),
  metadata: z.unknown().nullable().optional(),
  occurred_at: z.string(),
  href: z.string().nullable().optional(),
})
export type AuditEvent = z.infer<typeof AuditEvent>

export function listOf<T extends z.ZodTypeAny>(item: T) {
  return z.object({
    items: z.array(item),
    next_cursor: z.string().nullable(),
    total: z.number().optional(),
  })
}

export interface ListPayload<T> {
  items: T[]
  next_cursor: string | null
  total?: number
}

export type WorkOrderStatus = 'draft' | 'open' | 'in_progress' | 'on_hold' | 'done' | 'canceled' | 'skipped'
export type Priority = 'none' | 'low' | 'medium' | 'high' | 'critical'
export type WorkType = 'reactive' | 'preventive' | 'project' | 'event' | 'inspection' | 'safety' | 'procurement' | 'documentation'

export const WORK_ORDER_STATUSES: WorkOrderStatus[] = ['draft', 'open', 'in_progress', 'on_hold', 'done', 'canceled', 'skipped']
export const PRIORITIES: Priority[] = ['none', 'low', 'medium', 'high', 'critical']
export const WORK_TYPES: WorkType[] = ['reactive', 'preventive', 'project', 'event', 'inspection', 'safety', 'procurement', 'documentation']

export const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  open: 'Open',
  in_progress: 'In progress',
  on_hold: 'On hold',
  done: 'Done',
  canceled: 'Canceled',
  skipped: 'Skipped',
  planning: 'Planning',
  active: 'Active',
  completed: 'Completed',
  archived: 'Archived',
  online: 'Online',
  offline_planned: 'Offline (planned)',
  offline_unplanned: 'Offline (unplanned)',
  do_not_track: 'Not tracked',
  retired: 'Retired',
  planned: 'Planned',
  missed: 'Missed',
  invited: 'Invited',
  suspended: 'Suspended',
}

export const PRIORITY_LABELS: Record<Priority, string> = {
  none: 'None',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

export const WORK_TYPE_LABELS: Record<WorkType, string> = {
  reactive: 'Reactive',
  preventive: 'Preventive',
  project: 'Project',
  event: 'Event',
  inspection: 'Inspection',
  safety: 'Safety',
  procurement: 'Procurement',
  documentation: 'Documentation',
}

export function labelFor(value: string | null | undefined): string {
  if (!value) return '—'
  return STATUS_LABELS[value] ?? value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}
