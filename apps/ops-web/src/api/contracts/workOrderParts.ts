import { z } from 'zod'
import { listOf, LocationRef } from './common'

/**
 * Parts planned on a work order (`/work-orders/:id/parts`).
 *
 * Shapes mirror `asme/ops/serializers/work_order_parts.py`: every read and every
 * mutation answers with the same payload — the full line list, the readiness
 * summary and how many lines still hold an unissued reservation — so the screen
 * never has to merge a single row into a stale list.
 *
 * The part picker shapes at the bottom are the minimum of `GET /parts` and
 * `GET /parts/:id/inventory` this screen needs; the Parts Inventory feature owns
 * the full contract in `contracts/parts.ts`.
 */

/* Enumerations (asme/ops/models/inventory.py) ---------------------------------- */

export const WORK_ORDER_PART_READINESS = ['assigned', 'reserved', 'kitted', 'staged', 'issued'] as const
export type WorkOrderPartReadiness = (typeof WORK_ORDER_PART_READINESS)[number]

/** `readiness_summary` is a readiness, or `none` when the work order has no parts. */
export const READINESS_NONE = 'none'

export const READINESS_LABELS: Record<WorkOrderPartReadiness, string> = {
  assigned: 'Assigned',
  reserved: 'Reserved',
  kitted: 'Kitted',
  staged: 'Staged',
  issued: 'Issued',
}

/** Least advanced first, matching `work_order_parts.READINESS_RANK`. */
export const READINESS_RANK: Record<WorkOrderPartReadiness, number> = {
  assigned: 0,
  reserved: 1,
  kitted: 2,
  staged: 3,
  issued: 4,
}

export function readinessLabel(value: string | null | undefined): string {
  if (!value || value === READINESS_NONE) return 'No parts'
  return READINESS_LABELS[value as WorkOrderPartReadiness] ?? value.replace(/_/g, ' ')
}

export const STOCK_STATES = ['ok', 'low', 'out', 'untracked'] as const
export type StockState = (typeof STOCK_STATES)[number]

export const STOCK_STATE_LABELS: Record<StockState, string> = {
  ok: 'In stock',
  low: 'Low stock',
  out: 'Out of stock',
  untracked: 'Not tracked',
}

export function stockStateLabel(value: string | null | undefined): string {
  return STOCK_STATE_LABELS[(value ?? 'untracked') as StockState] ?? 'Not tracked'
}

/* Payload shapes ---------------------------------------------------------------- */

export const StockTotals = z.object({
  on_hand: z.number(),
  reserved: z.number(),
  available: z.number(),
  ordered: z.number(),
})
export type StockTotals = z.infer<typeof StockTotals>

export const ZERO_TOTALS: StockTotals = { on_hand: 0, reserved: 0, available: 0, ordered: 0 }

/** `part_ref` plus the chapter-wide stock picture the work-order screen shows. */
export const PartStockRef = z.looseObject({
  id: z.string(),
  name: z.string(),
  sku: z.string().nullable().optional(),
  unit: z.string().default('each'),
  stock_state: z.string().default('untracked'),
  totals: StockTotals.default(ZERO_TOTALS),
})
export type PartStockRef = z.infer<typeof PartStockRef>

export const WorkOrderPart = z.looseObject({
  id: z.string(),
  part: PartStockRef,
  location: LocationRef.nullable().optional(),
  quantity_planned: z.number(),
  quantity_reserved: z.number(),
  quantity_issued: z.number(),
  quantity_returned: z.number(),
  readiness: z.string(),
  note: z.string().nullable().optional(),
  created_at: z.string().optional(),
})
export type WorkOrderPart = z.infer<typeof WorkOrderPart>

/** Answer of every `/work-orders/:id/parts` route (`blueprints/ops/work_order_parts.py::_payload`). */
export const WorkOrderPartsPayload = z.object({
  items: z.array(WorkOrderPart),
  readiness_summary: z.string().default(READINESS_NONE),
  parts_outstanding: z.number().default(0),
})
export type WorkOrderPartsPayload = z.infer<typeof WorkOrderPartsPayload>

/* Quantity arithmetic ------------------------------------------------------------ */

/** Quantities are `Numeric(14, 3)`; round every derived number the same way so
 * 0.1 + 0.2 never reaches the screen. */
export function round3(value: number): number {
  return Math.round((value + Number.EPSILON) * 1000) / 1000
}

/** `3` → "3", `0.5` → "0.5"; never a trailing `.000`. */
export function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return String(round3(value))
}

export function formatQuantityUnit(value: number | null | undefined, unit: string | null | undefined): string {
  return `${formatQuantity(value)} ${unit || 'each'}`
}

/** Issued minus returned: what the work order is actually holding. */
export function outstandingQuantity(line: Pick<WorkOrderPart, 'quantity_issued' | 'quantity_returned'>): number {
  return round3(Math.max(line.quantity_issued - line.quantity_returned, 0))
}

/** Planned quantity still to be issued; returns put quantity back in play. */
export function remainingNeed(line: WorkOrderPart): number {
  return round3(Math.max(line.quantity_planned - outstandingQuantity(line), 0))
}

/** What `reserve` still accepts — the server caps at the same number. */
export function reservableQuantity(line: WorkOrderPart): number {
  return round3(Math.max(remainingNeed(line) - line.quantity_reserved, 0))
}

export function returnableQuantity(line: WorkOrderPart): number {
  return outstandingQuantity(line)
}

/**
 * How much stock the line still needs but the chapter does not have. Zero when
 * the part is untracked (nothing was ever received, so there is nothing to warn
 * about) or when availability covers the remaining need.
 */
export function stockShortfall(line: WorkOrderPart): number {
  if (line.part.stock_state === 'untracked') return 0
  const needed = reservableQuantity(line)
  if (needed <= 0) return 0
  return round3(Math.max(needed - line.part.totals.available, 0))
}

/** A line can only be taken off the work order while nothing is held or consumed. */
export function canRemoveLine(line: WorkOrderPart): boolean {
  return line.quantity_reserved <= 0 && line.quantity_issued <= 0
}

/* Line actions ------------------------------------------------------------------- */

export const PART_LINE_ACTIONS = ['reserve', 'release', 'kit', 'stage', 'issue', 'return'] as const
export type PartLineAction = (typeof PART_LINE_ACTIONS)[number]

export const PART_ACTION_LABELS: Record<PartLineAction, string> = {
  reserve: 'Reserve',
  release: 'Release',
  kit: 'Kit',
  stage: 'Stage',
  issue: 'Issue',
  return: 'Return',
}

/** Actions that ask for a quantity; `kit` and `stage` only move readiness. */
export const QUANTITY_ACTIONS: readonly PartLineAction[] = ['reserve', 'release', 'issue', 'return']

export function isQuantityAction(action: PartLineAction): boolean {
  return QUANTITY_ACTIONS.includes(action)
}

/* Form schemas -------------------------------------------------------------------- */

const QUANTITY_PATTERN = /^\d+(\.\d{1,3})?$/

function quantityField(missing: string) {
  return z
    .string()
    .trim()
    .min(1, missing)
    .regex(QUANTITY_PATTERN, 'Enter a quantity like 2 or 0.5, with at most three decimals.')
    .refine((value) => Number(value) > 0, 'Enter a quantity greater than zero.')
}

const noteField = z.string().trim().max(2000, 'Keep the note under 2000 characters.').optional().or(z.literal(''))

/** `POST /work-orders/:id/parts` form (`services/work_order_parts.py::ADD_SPEC`). */
export const AddPartInput = z.object({
  part_id: z.string().min(1, 'Choose a part.'),
  location_id: z.string().nullable(),
  quantity_planned: quantityField('Enter how many are needed.'),
  note: noteField,
})
export type AddPartInput = z.infer<typeof AddPartInput>

export interface AddPartPayload {
  part_id: string
  location_id: string | null
  quantity_planned: number
  note: string | null
}

export function toAddPartPayload(values: AddPartInput): AddPartPayload {
  return {
    part_id: values.part_id,
    location_id: values.location_id ?? null,
    quantity_planned: Number(values.quantity_planned),
    note: values.note?.trim() ? values.note.trim() : null,
  }
}

/** `PATCH /work-orders/:id/parts/:lineId` form (`UPDATE_SPEC`). */
export const UpdatePartInput = z.object({
  quantity_planned: quantityField('Enter how many are needed.'),
  note: noteField,
})
export type UpdatePartInput = z.infer<typeof UpdatePartInput>

export interface UpdatePartPayload {
  quantity_planned: number
  note: string | null
}

export function toUpdatePartPayload(values: UpdatePartInput): UpdatePartPayload {
  return {
    quantity_planned: Number(values.quantity_planned),
    note: values.note?.trim() ? values.note.trim() : null,
  }
}

/** Reserve / release / issue / return form (`QUANTITY_SPEC`). */
export const PartQuantityInput = z.object({
  quantity: quantityField('Enter a quantity.'),
  note: noteField,
})
export type PartQuantityInput = z.infer<typeof PartQuantityInput>

export interface PartQuantityPayload {
  quantity: number
  note?: string
}

export function toPartQuantityPayload(values: PartQuantityInput): PartQuantityPayload {
  const payload: PartQuantityPayload = { quantity: Number(values.quantity) }
  const note = values.note?.trim()
  if (note) payload.note = note
  return payload
}

/* Part picker (minimal `GET /parts` and `GET /parts/:id/inventory`) ---------------- */

export const PartPickerItem = z.looseObject({
  id: z.string(),
  name: z.string(),
  sku: z.string().nullable().optional(),
  unit: z.string().default('each'),
  stock_state: z.string().default('untracked'),
  totals: StockTotals.default(ZERO_TOTALS),
  default_location: LocationRef.nullable().optional(),
  is_active: z.boolean().optional(),
})
export type PartPickerItem = z.infer<typeof PartPickerItem>

export const PartPickerList = listOf(PartPickerItem)
export type PartPickerList = z.infer<typeof PartPickerList>

/** One row of `GET /parts/:id/inventory` → `balances` (`serializers/parts.py::balance`). */
export const PartBalance = z.looseObject({
  location: LocationRef.nullable(),
  on_hand: z.number(),
  reserved: z.number(),
  available: z.number(),
})
export type PartBalance = z.infer<typeof PartBalance>

export const PartInventory = z.object({
  balances: z.array(PartBalance),
  totals: StockTotals.default(ZERO_TOTALS),
})
export type PartInventory = z.infer<typeof PartInventory>
