import { z } from 'zod'
import { AuditEvent, listOf, LocationRef, ProjectRef, TeamRef, UserRef } from './common'

/* Enumerations (asme/ops/models/structure.py) ------------------------------- */

export const ASSET_STATUSES = ['online', 'offline_planned', 'offline_unplanned', 'do_not_track', 'retired'] as const
export type AssetStatus = (typeof ASSET_STATUSES)[number]

export const ASSET_CRITICALITIES = ['none', 'low', 'medium', 'high'] as const
export type AssetCriticality = (typeof ASSET_CRITICALITIES)[number]

export const DOWNTIME_TYPES = ['planned', 'unplanned'] as const
export type DowntimeType = (typeof DOWNTIME_TYPES)[number]

export const OFFLINE_STATUSES: readonly AssetStatus[] = ['offline_planned', 'offline_unplanned']

export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  online: 'Online',
  offline_planned: 'Offline (planned)',
  offline_unplanned: 'Offline (unplanned)',
  do_not_track: 'Not tracked',
  retired: 'Retired',
}

export const ASSET_CRITICALITY_LABELS: Record<AssetCriticality, string> = {
  none: 'None',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
}

export const DOWNTIME_TYPE_LABELS: Record<DowntimeType, string> = {
  planned: 'Planned',
  unplanned: 'Unplanned',
}

export function isOfflineStatus(status: string | null | undefined): boolean {
  return Boolean(status && (OFFLINE_STATUSES as readonly string[]).includes(status))
}

/* Asset types (serializers/assets.py::asset_type) ----------------------------- */

export const AssetTypeBrief = z.object({ id: z.string(), name: z.string(), color: z.string().optional() })
export type AssetTypeBrief = z.infer<typeof AssetTypeBrief>

export const AssetType = z.looseObject({
  id: z.string(),
  name: z.string(),
  color: z.string(),
  icon: z.string().optional(),
  asset_count: z.number().optional(),
})
export type AssetType = z.infer<typeof AssetType>

export const AssetTypeList = listOf(AssetType)

/* Asset (serializers/assets.py::asset) ---------------------------------------- */

export const Asset = z.looseObject({
  id: z.string(),
  name: z.string(),
  code: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  parent_id: z.string().nullable().optional(),
  project: ProjectRef.nullable().optional(),
  location: LocationRef.nullable().optional(),
  team: TeamRef.nullable().optional(),
  owner: UserRef.nullable().optional(),
  manufacturer: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  serial_number: z.string().nullable().optional(),
  purchase_date: z.string().nullable().optional(),
  purchase_cost: z.number().nullable().optional(),
  warranty_end: z.string().nullable().optional(),
  criticality: z.string().optional(),
  status: z.string(),
  qr_code: z.string().nullable().optional(),
  custom_fields: z.record(z.string(), z.unknown()).optional(),
  is_active: z.boolean().optional(),
  types: z.array(AssetTypeBrief).default([]),
  child_count: z.number().optional(),
  open_work_order_count: z.number().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
})
export type Asset = z.infer<typeof Asset>

export const AssetList = listOf(Asset)
export type AssetList = z.infer<typeof AssetList>

/** `GET /assets?view=hierarchy` node: an asset plus nested `children`. */
export interface AssetHierarchyNode extends Asset {
  children: AssetHierarchyNode[]
}

export const AssetHierarchyNode: z.ZodType<AssetHierarchyNode> = z.lazy(() =>
  Asset.extend({ children: z.array(AssetHierarchyNode).default([]) }),
) as unknown as z.ZodType<AssetHierarchyNode>

export const AssetHierarchy = z.object({ items: z.array(AssetHierarchyNode), total: z.number().optional() })

/* Status history and timeline (serializers/assets.py) ------------------------ */

export const AssetStatusHistory = z.looseObject({
  id: z.string(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  downtime_type: z.string().nullable().optional(),
  downtime_reason: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  ended_at: z.string().nullable().optional(),
  changed_by: UserRef.nullable().optional(),
  work_order_id: z.string().nullable().optional(),
})
export type AssetStatusHistory = z.infer<typeof AssetStatusHistory>

const TimelineStatus = AssetStatusHistory.extend({ kind: z.literal('status'), at: z.string() })
const TimelineAudit = AuditEvent.extend({ kind: z.literal('audit'), at: z.string() })
const TimelineWorkOrder = z.looseObject({ kind: z.literal('work_order'), id: z.string(), number: z.number(), title: z.string(), status: z.string(), at: z.string() })

export const AssetTimelineEntry = z.discriminatedUnion('kind', [TimelineStatus, TimelineAudit, TimelineWorkOrder])
export type AssetTimelineEntry = z.infer<typeof AssetTimelineEntry>

export const AssetHistory = z.object({ items: z.array(AssetTimelineEntry) })

/** Rows of `GET /work-orders?filter[asset]=…&tab=todo` shown on the asset detail. */
export const AssetOpenWorkOrder = z.looseObject({
  id: z.string(),
  number: z.number(),
  title: z.string(),
  status: z.string(),
  priority: z.string().optional(),
  due_at: z.string().nullable().optional(),
  is_overdue: z.boolean().optional(),
  assignees: z.array(UserRef).default([]),
})
export type AssetOpenWorkOrder = z.infer<typeof AssetOpenWorkOrder>
export const AssetOpenWorkOrderList = listOf(AssetOpenWorkOrder)

/* Form schemas ---------------------------------------------------------------- */

const optionalText = (max: number) => z.string().trim().max(max, `Keep this under ${max} characters.`).optional().or(z.literal(''))
const optionalDate = z
  .string()
  .regex(/^(\d{4}-\d{2}-\d{2})?$/, 'Enter a date as YYYY-MM-DD.')
  .optional()
  .or(z.literal(''))

/** Create/edit form values. Empty strings mean "not set"; `toAssetPayload` turns them into the JSON body. */
export const AssetInput = z
  .object({
    name: z.string().trim().min(1, 'Give the asset a name.').max(200, 'Keep the name under 200 characters.'),
    code: optionalText(60),
    description: z.string().trim().optional().or(z.literal('')),
    type_ids: z.array(z.string()).max(50, 'Choose at most 50 types.'),
    parent_id: z.string().nullable(),
    project_id: z.string().nullable(),
    location_id: z.string().nullable(),
    responsible_team_id: z.string().nullable(),
    owner_user_id: z.number().nullable(),
    manufacturer: optionalText(160),
    model: optionalText(160),
    serial_number: optionalText(160),
    purchase_date: optionalDate,
    purchase_cost: z
      .string()
      .trim()
      .regex(/^(\d+(\.\d{1,2})?)?$/, 'Enter an amount like 1099.50.')
      .optional()
      .or(z.literal('')),
    warranty_end: optionalDate,
    criticality: z.enum(ASSET_CRITICALITIES),
    status: z.enum(ASSET_STATUSES),
  })
  .superRefine((values, ctx) => {
    if (values.purchase_date && values.warranty_end && values.warranty_end < values.purchase_date) {
      ctx.addIssue({ code: 'custom', path: ['warranty_end'], message: 'Warranty end must be on or after the purchase date.' })
    }
  })
export type AssetInput = z.infer<typeof AssetInput>

/** JSON body for `POST /assets` (with `status`) or `PATCH /assets/:id` (without). */
export type AssetPayload = {
  name: string
  code: string | null
  description: string | null
  type_ids: string[]
  parent_id: string | null
  project_id: string | null
  location_id: string | null
  responsible_team_id: string | null
  owner_user_id: number | null
  manufacturer: string | null
  model: string | null
  serial_number: string | null
  purchase_date: string | null
  purchase_cost: number | null
  warranty_end: string | null
  criticality: AssetCriticality
  status?: AssetStatus
}

const blankToNull = (value: string | undefined | null): string | null => {
  const text = (value ?? '').trim()
  return text ? text : null
}

export function toAssetPayload(values: AssetInput, mode: 'create' | 'edit'): AssetPayload {
  const payload: AssetPayload = {
    name: values.name.trim(),
    code: blankToNull(values.code),
    description: blankToNull(values.description),
    type_ids: values.type_ids,
    parent_id: values.parent_id ?? null,
    project_id: values.project_id ?? null,
    location_id: values.location_id ?? null,
    responsible_team_id: values.responsible_team_id ?? null,
    owner_user_id: values.owner_user_id ?? null,
    manufacturer: blankToNull(values.manufacturer),
    model: blankToNull(values.model),
    serial_number: blankToNull(values.serial_number),
    purchase_date: blankToNull(values.purchase_date),
    purchase_cost: values.purchase_cost && values.purchase_cost.trim() ? Number(values.purchase_cost) : null,
    warranty_end: blankToNull(values.warranty_end),
    criticality: values.criticality,
  }
  if (mode === 'create') payload.status = values.status
  return payload
}

/** `POST /assets/:id/status` body (services/assets.py::STATUS_SPEC). */
export const AssetStatusInput = z.object({
  status: z.enum(ASSET_STATUSES, { message: 'Choose a status.' }),
  downtime_type: z.enum(DOWNTIME_TYPES).nullable(),
  downtime_reason: optionalText(160),
  note: z.string().trim().optional().or(z.literal('')),
})
export type AssetStatusInput = z.infer<typeof AssetStatusInput>

export type AssetStatusPayload = { status: AssetStatus; downtime_type?: DowntimeType; downtime_reason?: string; note?: string }

export function toAssetStatusPayload(values: AssetStatusInput): AssetStatusPayload {
  const payload: AssetStatusPayload = { status: values.status }
  if (isOfflineStatus(values.status)) {
    if (values.downtime_type) payload.downtime_type = values.downtime_type
    if (values.downtime_reason?.trim()) payload.downtime_reason = values.downtime_reason.trim()
  }
  if (values.note?.trim()) payload.note = values.note.trim()
  return payload
}

/** `POST /asset-types` body (services/assets.py::ASSET_TYPE_SPEC). */
export const AssetTypeInput = z.object({
  name: z.string().trim().min(1, 'Give the type a name.').max(120, 'Keep the name under 120 characters.'),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/, 'Pick a colour.'),
})
export type AssetTypeInput = z.infer<typeof AssetTypeInput>

/* List parameters --------------------------------------------------------------- */

export const ASSET_SORTS = ['name', '-name', 'status', '-status', 'criticality', '-criticality', 'updated_at', '-updated_at', 'created_at', '-created_at'] as const
export type AssetSort = (typeof ASSET_SORTS)[number]

export interface AssetListParams {
  q?: string
  status?: string[]
  criticality?: string[]
  type?: string[]
  project?: string[]
  location?: string[]
  team?: string[]
  parent?: string
  active?: 'true' | 'false'
  sort?: string
  limit?: number
  cursor?: string | null
}

export interface AssetHierarchyParams {
  project?: string[]
  location?: string[]
}
