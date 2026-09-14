import { PRIORITIES, WORK_TYPES, type Priority, type WorkType } from '@/api/contracts/common'
import { EMPTY_WORK_ORDER_FORM, estimateToMinutes, minutesToEstimate, type WorkOrderDetail, type WorkOrderFormValues, type WorkOrderInput } from '@/api/contracts/work-orders'
import { fromDateTimeLocal, toDateTimeLocal } from '@/lib/dates'

/** Form values -> `POST /work-orders` / `PATCH /work-orders/:id` body (CREATE_SPEC field names). */
export function toWorkOrderInput(values: WorkOrderFormValues, options: { draft?: boolean; publish?: boolean } = {}): WorkOrderInput {
  const input: WorkOrderInput = {
    title: values.title.trim(),
    description: values.description.trim() || null,
    priority: values.priority,
    work_type: values.work_type,
    project_id: values.project_id ?? null,
    location_id: values.location_id ?? null,
    primary_asset_id: values.primary_asset_id ?? null,
    team_id: values.team_id ?? null,
    vendor_id: values.vendor_id ?? null,
    parent_id: values.parent_id ?? null,
    start_at: fromDateTimeLocal(values.start_at),
    due_at: fromDateTimeLocal(values.due_at),
    estimated_minutes: estimateToMinutes(values.estimated_hours, values.estimated_minutes),
    budget_code: values.budget_code.trim() || null,
    assignee_user_ids: values.assignee_user_ids,
    watcher_user_ids: values.watcher_user_ids,
    category_ids: values.category_ids,
  }
  if (options.draft) input.draft = true
  if (options.publish) input.status = 'open'
  return input
}

/** Existing work order -> form values for the edit pane. */
export function fromWorkOrderDetail(wo: WorkOrderDetail): WorkOrderFormValues {
  return {
    ...EMPTY_WORK_ORDER_FORM,
    title: wo.title,
    description: wo.description ?? '',
    sub_work_orders: [],
    project_id: wo.project?.id ?? null,
    location_id: wo.location?.id ?? null,
    primary_asset_id: wo.asset?.id ?? null,
    assignee_user_ids: wo.assignees.map((u) => u.id),
    team_id: wo.team?.id ?? null,
    ...minutesToEstimate(wo.estimated_minutes),
    due_at: toDateTimeLocal(wo.due_at),
    start_at: toDateTimeLocal(wo.start_at),
    work_type: (WORK_TYPES as string[]).includes(wo.work_type) ? (wo.work_type as WorkType) : 'reactive',
    priority: (PRIORITIES as string[]).includes(wo.priority) ? (wo.priority as Priority) : 'none',
    category_ids: wo.categories.map((c) => c.id),
    vendor_id: wo.vendor?.id ?? null,
    budget_code: wo.budget_code ?? '',
    watcher_user_ids: wo.watchers.map((u) => u.id),
    parent_id: wo.parent_id ?? null,
  }
}

/** Prefill for the create pane from `?project=&category=&parent=&asset=&location=&team=`. */
export function prefillFromParams(params: URLSearchParams): Partial<WorkOrderFormValues> {
  const prefill: Partial<WorkOrderFormValues> = {}
  const project = params.get('project')
  const category = params.get('category')
  const parent = params.get('parent')
  const asset = params.get('asset')
  const location = params.get('location')
  const team = params.get('team')
  if (project) prefill.project_id = project
  if (category) prefill.category_ids = category.split(',').filter(Boolean)
  if (parent) prefill.parent_id = parent
  if (asset) prefill.primary_asset_id = asset
  if (location) prefill.location_id = location
  if (team) prefill.team_id = team
  return prefill
}

/** Server-side field names that map onto a differently named form field. */
export const SERVER_FIELD_MAP: Record<string, keyof WorkOrderFormValues> = {
  estimated_minutes: 'estimated_minutes',
  assignee_team_ids: 'team_id',
  asset_ids: 'primary_asset_id',
}
