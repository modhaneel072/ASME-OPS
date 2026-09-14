import { z } from 'zod'
import { AssetRef, CategoryRef, listOf, LocationRef, PRIORITIES, ProjectRef, TeamRef, UserRef, VendorRef, WORK_TYPES } from './common'

/* Shapes (asme/ops/serializers/work_orders.py) -------------------------------- */

export const SubWorkOrderCounts = z.object({ total: z.number(), done: z.number() })

export const WorkOrder = z.looseObject({
  id: z.string(),
  number: z.number(),
  title: z.string(),
  description: z.string().nullable().optional(),
  status: z.string(),
  priority: z.string(),
  work_type: z.string(),
  project: ProjectRef.nullable().optional(),
  location: LocationRef.nullable().optional(),
  asset: AssetRef.nullable().optional(),
  team: TeamRef.nullable().optional(),
  assignees: z.array(UserRef).default([]),
  assignee_teams: z.array(TeamRef).default([]),
  watchers: z.array(UserRef).default([]),
  categories: z.array(CategoryRef).default([]),
  vendor: VendorRef.nullable().optional(),
  parent_id: z.string().nullable().optional(),
  parent_number: z.number().nullable().optional(),
  parent_completion_policy: z.string().nullable().optional(),
  sub_work_orders: SubWorkOrderCounts.default({ total: 0, done: 0 }),
  start_at: z.string().nullable().optional(),
  due_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  canceled_at: z.string().nullable().optional(),
  estimated_minutes: z.number().nullable().optional(),
  actual_minutes: z.number().default(0),
  is_overdue: z.boolean().default(false),
  is_blocked: z.boolean().default(false),
  budget_code: z.string().nullable().optional(),
  completion_note: z.string().nullable().optional(),
  created_by: UserRef.nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type WorkOrder = z.infer<typeof WorkOrder>

export const StatusHistoryEntry = z.looseObject({
  id: z.string(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  changed_by: UserRef.nullable().optional(),
  note: z.string().nullable().optional(),
  changed_at: z.string(),
})
export type StatusHistoryEntry = z.infer<typeof StatusHistoryEntry>

export const TimeEntry = z.looseObject({
  id: z.string(),
  user: UserRef.nullable().optional(),
  minutes: z.number(),
  started_at: z.string().nullable().optional(),
  ended_at: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
})
export type TimeEntry = z.infer<typeof TimeEntry>

export const CostEntry = z.looseObject({
  id: z.string(),
  type: z.string(),
  amount: z.number().nullable(),
  vendor: VendorRef.nullable().optional(),
  description: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
})
export type CostEntry = z.infer<typeof CostEntry>

export const WorkOrderStub = z.object({ id: z.string(), number: z.number(), title: z.string(), status: z.string() })
export type WorkOrderStub = z.infer<typeof WorkOrderStub>

export const DependencyEntry = z.looseObject({
  id: z.string(),
  dependency_type: z.string().optional(),
  work_order: WorkOrderStub,
})
export type DependencyEntry = z.infer<typeof DependencyEntry>

export const WorkOrderDetail = WorkOrder.extend({
  status_history: z.array(StatusHistoryEntry).default([]),
  time_entries: z.array(TimeEntry).default([]),
  cost_entries: z.array(CostEntry).default([]),
  dependencies: z.object({ blocked_by: z.array(DependencyEntry).default([]), blocking: z.array(DependencyEntry).default([]) }).default({ blocked_by: [], blocking: [] }),
  children: z.array(WorkOrder).default([]),
  related_assets: z.array(AssetRef).default([]),
})
export type WorkOrderDetail = z.infer<typeof WorkOrderDetail>

export const TabCounts = z.object({ todo: z.number(), done: z.number() })
export type TabCounts = z.infer<typeof TabCounts>

export const WorkOrderList = listOf(WorkOrder).extend({ tabs: TabCounts.optional() })
export type WorkOrderList = z.infer<typeof WorkOrderList>

export const CompleteResponse = z.object({ work_order: WorkOrderDetail, follow_up: WorkOrder.nullable().optional() })
export type CompleteResponse = z.infer<typeof CompleteResponse>

/* List parameters (services/work_orders.py LIST_FILTERS / LIST_SORTS) --------- */

export const WORK_ORDER_FILTER_NAMES = ['status', 'priority', 'work_type', 'project', 'location', 'asset', 'team', 'assignee', 'category', 'due', 'created_by', 'parent', 'vendor'] as const
export type WorkOrderFilterName = (typeof WORK_ORDER_FILTER_NAMES)[number]
export type WorkOrderFilters = Partial<Record<WorkOrderFilterName, string[]>>

export type WorkOrderTab = 'todo' | 'done' | 'all'
export type WorkOrderSort = 'priority' | '-priority' | 'due_at' | '-due_at' | 'updated_at' | '-updated_at' | 'created_at' | '-created_at' | 'number' | '-number' | 'title' | '-title'
export const DEFAULT_WORK_ORDER_SORT: WorkOrderSort = '-updated_at'

export const WORK_ORDER_SORT_OPTIONS: Array<{ value: WorkOrderSort; label: string }> = [
  { value: '-priority', label: 'Priority: Highest First' },
  { value: 'due_at', label: 'Due Date: Soonest First' },
  { value: '-updated_at', label: 'Last Updated' },
  { value: '-created_at', label: 'Created Date' },
  { value: 'number', label: 'Number' },
  { value: 'title', label: 'Title' },
]

export const DUE_FILTER_OPTIONS = [
  { value: 'overdue', label: 'Overdue' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'This week' },
  { value: 'month', label: 'This month' },
  { value: 'none', label: 'No due date' },
]

export const COST_TYPES = ['parts', 'labor', 'vendor', 'other'] as const
export type CostType = (typeof COST_TYPES)[number]
export const COST_TYPE_LABELS: Record<CostType, string> = { parts: 'Parts', labor: 'Labor', vendor: 'Vendor', other: 'Other' }

export const ASSET_STATUSES = ['online', 'offline_planned', 'offline_unplanned', 'do_not_track', 'retired'] as const
export const DOWNTIME_TYPES = ['planned', 'unplanned'] as const

export interface WorkOrderListParams {
  q?: string
  tab?: WorkOrderTab
  sort?: WorkOrderSort | string
  filters?: WorkOrderFilters
  limit?: number
}

/* Request bodies (services/work_orders.py CREATE_SPEC and friends) ------------ */

export interface WorkOrderInput {
  title: string
  description?: string | null
  priority?: string
  work_type?: string
  project_id?: string | null
  location_id?: string | null
  primary_asset_id?: string | null
  team_id?: string | null
  vendor_id?: string | null
  parent_id?: string | null
  start_at?: string | null
  due_at?: string | null
  estimated_minutes?: number | null
  budget_code?: string | null
  parent_completion_policy?: 'manual' | 'auto'
  assignee_user_ids?: number[]
  assignee_team_ids?: string[]
  watcher_user_ids?: number[]
  category_ids?: string[]
  asset_ids?: string[]
  draft?: boolean
  /** Only meaningful on PATCH: publishes a draft. */
  status?: 'open'
}

export interface TimeEntryInput {
  minutes?: number | null
  started_at?: string | null
  ended_at?: string | null
  note?: string | null
  user_id?: number
}

export interface CostEntryInput {
  type: CostType | string
  amount: number
  vendor_id?: string | null
  description?: string | null
}

export interface CompleteInput {
  note?: string | null
  time_entries?: TimeEntryInput[]
  cost_entries?: CostEntryInput[]
  asset_status?: { status: string; downtime_type?: string | null; downtime_reason?: string | null; note?: string | null } | null
  follow_up?: { title: string; description?: string | null; priority?: string; work_type?: string; due_at?: string | null } | null
}

export type TransitionAction = 'start' | 'hold' | 'resume' | 'cancel' | 'reopen'

/* Form schema (create / edit pane) ------------------------------------------- */

const wholeNumber = z.string().regex(/^\d*$/, 'Use whole numbers.')

export const WorkOrderFormValues = z.object({
  title: z.string().trim().min(1, 'Give the work order a title.').max(240, 'Keep the title under 240 characters.'),
  description: z.string().max(20000, 'Keep the description under 20,000 characters.'),
  sub_work_orders: z.array(z.object({ title: z.string().trim().max(240, 'Keep the title under 240 characters.') })),
  project_id: z.string().nullable(),
  location_id: z.string().nullable(),
  primary_asset_id: z.string().nullable(),
  assignee_user_ids: z.array(z.number()),
  team_id: z.string().nullable(),
  estimated_hours: wholeNumber,
  estimated_minutes: wholeNumber,
  due_at: z.string(),
  start_at: z.string(),
  work_type: z.enum(WORK_TYPES),
  priority: z.enum(PRIORITIES),
  category_ids: z.array(z.string()),
  vendor_id: z.string().nullable(),
  budget_code: z.string().trim().max(60, 'Keep the budget code under 60 characters.'),
  watcher_user_ids: z.array(z.number()),
  parent_id: z.string().nullable(),
})
export type WorkOrderFormValues = z.infer<typeof WorkOrderFormValues>

export const EMPTY_WORK_ORDER_FORM: WorkOrderFormValues = {
  title: '',
  description: '',
  sub_work_orders: [],
  project_id: null,
  location_id: null,
  primary_asset_id: null,
  assignee_user_ids: [],
  team_id: null,
  estimated_hours: '',
  estimated_minutes: '',
  due_at: '',
  start_at: '',
  work_type: 'reactive',
  priority: 'none',
  category_ids: [],
  vendor_id: null,
  budget_code: '',
  watcher_user_ids: [],
  parent_id: null,
}

/** Combined estimate in minutes, or null when both inputs are blank. */
export function estimateToMinutes(hours: string, minutes: string): number | null {
  const h = hours.trim() === '' ? 0 : Number(hours)
  const m = minutes.trim() === '' ? 0 : Number(minutes)
  if (hours.trim() === '' && minutes.trim() === '') return null
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null
  return h * 60 + m
}

export function minutesToEstimate(total: number | null | undefined): { estimated_hours: string; estimated_minutes: string } {
  if (total === null || total === undefined) return { estimated_hours: '', estimated_minutes: '' }
  return { estimated_hours: String(Math.floor(total / 60)), estimated_minutes: String(total % 60) }
}
