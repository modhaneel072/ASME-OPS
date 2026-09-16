import { z } from 'zod'
import { AssetRef, LocationRef, UserRef, VendorRef, listOf } from './common'

/**
 * Parts inventory contracts (`/parts`, `/part-types`, `/inventory/*`).
 *
 * Shapes mirror `asme/ops/serializers/parts.py` and the form schemas mirror the
 * module-level validation specs in `asme/ops/services/parts.py` and
 * `asme/ops/services/inventory.py`, so a form rejects locally exactly what the
 * server would reject remotely. Quantities are `Numeric(14, 3)` and unit costs
 * `Numeric(12, 4)`; both travel as JSON numbers and are entered as text so a
 * half-typed "0." never becomes `NaN`.
 */

/* Enumerations (asme/ops/models/inventory.py) ---------------------------------- */

export const PART_UNITS = ['each', 'pack', 'box', 'pair', 'set', 'g', 'kg', 'lb', 'oz', 'm', 'cm', 'mm', 'ft', 'in', 'roll', 'spool', 'sheet', 'L', 'mL'] as const
export type PartUnit = (typeof PART_UNITS)[number]

export const STOCK_STATES = ['ok', 'low', 'out', 'untracked'] as const
export type StockState = (typeof STOCK_STATES)[number]

export const STOCK_STATE_LABELS: Record<StockState, string> = {
  ok: 'In stock',
  low: 'Low stock',
  out: 'Out of stock',
  untracked: 'Not tracked',
}

export function stockStateLabel(value: string | null | undefined): string {
  return STOCK_STATE_LABELS[(value ?? 'untracked') as StockState] ?? STOCK_STATE_LABELS.untracked
}

export const INVENTORY_TRANSACTION_TYPES = ['receipt', 'issue', 'return', 'adjustment', 'transfer', 'reservation', 'release', 'cycle_count', 'scrap'] as const
export type InventoryTransactionType = (typeof INVENTORY_TRANSACTION_TYPES)[number]

export const TRANSACTION_TYPE_LABELS: Record<InventoryTransactionType, string> = {
  receipt: 'Receipt',
  issue: 'Issue',
  return: 'Return',
  adjustment: 'Adjustment',
  transfer: 'Transfer',
  reservation: 'Reservation',
  release: 'Release',
  cycle_count: 'Cycle count',
  scrap: 'Scrap',
}

export function transactionTypeLabel(value: string | null | undefined): string {
  if (!value) return '—'
  return TRANSACTION_TYPE_LABELS[value as InventoryTransactionType] ?? value.replace(/_/g, ' ')
}

/** What `POST /parts/:id/transactions` accepts (`services/inventory.py::DIRECT_TYPES`). */
export const MOVEMENT_TYPES = ['receipt', 'issue', 'return', 'adjustment', 'scrap'] as const
export type MovementType = (typeof MOVEMENT_TYPES)[number]

/** Imperative labels: these name a button, not a ledger row. */
export const MOVEMENT_LABELS: Record<MovementType, string> = {
  receipt: 'Receive',
  issue: 'Issue',
  return: 'Return',
  adjustment: 'Adjust',
  scrap: 'Scrap',
}

export const ADJUSTMENT_DIRECTIONS = ['increase', 'decrease'] as const
export type AdjustmentDirection = (typeof ADJUSTMENT_DIRECTIONS)[number]

/** A note is mandatory for these two — the ledger row is otherwise unexplainable. */
export const NOTE_REQUIRED_TYPES: readonly MovementType[] = ['adjustment', 'scrap']

/** Only these may carry a work order; only a receipt may carry a unit cost. */
export const WORK_ORDER_TYPES: readonly MovementType[] = ['issue', 'return']

export const MAX_VENDOR_LINKS = 50
export const MAX_ASSET_LINKS = 100

/* Numbers ---------------------------------------------------------------------- */

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

/** Unit costs keep up to four decimals (`Numeric(12, 4)`). */
export function formatUnitCost(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value)
}

/* Part types (serializers/parts.py::part_type) --------------------------------- */

export const PartTypeBrief = z.object({ id: z.string(), name: z.string(), color: z.string().optional(), icon: z.string().optional() })
export type PartTypeBrief = z.infer<typeof PartTypeBrief>

export const PartType = z.looseObject({
  id: z.string(),
  name: z.string(),
  color: z.string().default('#475569'),
  icon: z.string().optional(),
  part_count: z.number().optional(),
})
export type PartType = z.infer<typeof PartType>

export const PartTypeList = listOf(PartType)

/* Parts ------------------------------------------------------------------------ */

export const StockTotals = z.object({
  on_hand: z.number(),
  reserved: z.number(),
  available: z.number(),
  ordered: z.number(),
})
export type StockTotals = z.infer<typeof StockTotals>

export const ZERO_TOTALS: StockTotals = { on_hand: 0, reserved: 0, available: 0, ordered: 0 }

export const PartRef = z.looseObject({
  id: z.string(),
  name: z.string(),
  sku: z.string().nullable().optional(),
  unit: z.string().default('each'),
})
export type PartRef = z.infer<typeof PartRef>

export const Part = PartRef.extend({
  description: z.string().nullable().optional(),
  part_type: PartTypeBrief.nullable().optional(),
  manufacturer: z.string().nullable().optional(),
  manufacturer_part_number: z.string().nullable().optional(),
  unit_cost: z.number().nullable().optional(),
  is_critical: z.boolean().default(false),
  minimum_stock: z.number().nullable().optional(),
  maximum_stock: z.number().nullable().optional(),
  reorder_quantity: z.number().nullable().optional(),
  default_location: LocationRef.nullable().optional(),
  qr_code: z.string().nullable().optional(),
  is_active: z.boolean().default(true),
  totals: StockTotals.default(ZERO_TOTALS),
  stock_state: z.string().default('untracked'),
  preferred_vendor: VendorRef.nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
})
export type Part = z.infer<typeof Part>

export const StockCounts = z.object({ low: z.number(), out: z.number() })
export type StockCounts = z.infer<typeof StockCounts>

/** `GET /parts`: a page of parts plus the tab badges, which ignore `filter[stock]`. */
export const PartList = listOf(Part).extend({ stock_counts: StockCounts.default({ low: 0, out: 0 }) })
export type PartList = z.infer<typeof PartList>

/** One row of `GET /parts/:id/inventory` → `balances` (`serializers/parts.py::balance`). */
export const PartBalance = z.looseObject({
  location: LocationRef.nullable(),
  on_hand: z.number(),
  reserved: z.number(),
  available: z.number(),
})
export type PartBalance = z.infer<typeof PartBalance>

export const PartVendorLink = z.looseObject({
  vendor: VendorRef,
  vendor_part_number: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  preferred: z.boolean().default(false),
  last_price: z.number().nullable().optional(),
  last_ordered_at: z.string().nullable().optional(),
})
export type PartVendorLink = z.infer<typeof PartVendorLink>

export const PurchaseRequestRef = z.looseObject({
  id: z.string(),
  number: z.number(),
  display_number: z.string(),
  title: z.string(),
  status: z.string(),
})
export type PurchaseRequestRef = z.infer<typeof PurchaseRequestRef>

export const OpenPurchaseRequest = PurchaseRequestRef.extend({ outstanding_quantity: z.number().default(0) })
export type OpenPurchaseRequest = z.infer<typeof OpenPurchaseRequest>

export const WorkOrderBrief = z.object({ id: z.string(), number: z.number(), title: z.string() })
export type WorkOrderBrief = z.infer<typeof WorkOrderBrief>

export const InventoryTransaction = z.looseObject({
  id: z.string(),
  type: z.string(),
  part: PartRef.nullable(),
  location: LocationRef.nullable(),
  quantity: z.number(),
  on_hand_delta: z.number(),
  reserved_delta: z.number(),
  on_hand_after: z.number(),
  reserved_after: z.number(),
  counted_quantity: z.number().nullable().optional(),
  unit_cost: z.number().nullable().optional(),
  work_order: WorkOrderBrief.nullable().optional(),
  purchase_request: PurchaseRequestRef.nullable().optional(),
  reference_transaction_id: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  created_by: UserRef.nullable().optional(),
  created_at: z.string(),
})
export type InventoryTransaction = z.infer<typeof InventoryTransaction>

export const InventoryTransactionList = listOf(InventoryTransaction)
export type InventoryTransactionList = z.infer<typeof InventoryTransactionList>

export const PartDetail = Part.extend({
  balances: z.array(PartBalance).default([]),
  vendors: z.array(PartVendorLink).default([]),
  assets: z.array(AssetRef).default([]),
  open_purchase_requests: z.array(OpenPurchaseRequest).default([]),
  recent_transactions: z.array(InventoryTransaction).default([]),
})
export type PartDetail = z.infer<typeof PartDetail>

/** `POST /inventory/cycle-counts` answer. */
export const CycleCountResult = z.object({
  lines: z.array(z.object({ part: PartRef.nullable(), expected: z.number(), counted: z.number(), delta: z.number() })),
})
export type CycleCountResult = z.infer<typeof CycleCountResult>

/** `POST /purchase-requests/from-low-stock` answer (the drafts it created). */
export const CreatedPurchaseRequests = z.object({ purchase_requests: z.array(PurchaseRequestRef) })
export type CreatedPurchaseRequests = z.infer<typeof CreatedPurchaseRequests>

/* Form schemas ------------------------------------------------------------------ */

const QUANTITY_PATTERN = /^\d+(\.\d{1,3})?$/
const OPTIONAL_UNIT_COST_PATTERN = /^$|^\d+(\.\d{1,4})?$/
const QUANTITY_MESSAGE = 'Enter a quantity like 2 or 0.5, with at most three decimals.'
const UNIT_COST_MESSAGE = 'Enter an amount like 12.50, with at most four decimals.'
const WEBSITE_RE = /^https?:\/\/\S+$/i

/** Optional unit-cost text: blank means "not set". */
const optionalUnitCost = z.string().trim().regex(OPTIONAL_UNIT_COST_PATTERN, UNIT_COST_MESSAGE).optional().or(z.literal(''))

/** Optional quantity text: blank means "not set". */
const optionalQuantity = z
  .string()
  .trim()
  .regex(/^$|^\d+(\.\d{1,3})?$/, QUANTITY_MESSAGE)
  .optional()
  .or(z.literal(''))

/** Required quantity text; zero is allowed (a cycle count may find an empty shelf). */
function quantityText(missing: string) {
  return z.string().trim().min(1, missing).regex(QUANTITY_PATTERN, QUANTITY_MESSAGE)
}

/** Required quantity text that must be greater than zero, as every movement is. */
function positiveQuantity(missing: string) {
  return quantityText(missing).refine((value) => Number(value) > 0, 'Enter a quantity greater than zero.')
}

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `Keep this under ${max} characters.`)
    .optional()
    .or(z.literal(''))

const noteField = z.string().trim().max(4000, 'Keep the note under 4000 characters.').optional().or(z.literal(''))

const blankToNull = (value: string | null | undefined): string | null => {
  const text = (value ?? '').trim()
  return text ? text : null
}

const numberOrNull = (value: string | null | undefined): number | null => {
  const text = (value ?? '').trim()
  return text ? Number(text) : null
}

/** Create/edit part form (`services/parts.py::PART_SPEC` + `_check_references`). */
export const PartInput = z
  .object({
    name: z.string().trim().min(1, 'Give the part a name.').max(200, 'Keep the name under 200 characters.'),
    sku: optionalText(60),
    description: z.string().trim().optional().or(z.literal('')),
    part_type_id: z.string().nullable(),
    manufacturer: optionalText(160),
    manufacturer_part_number: optionalText(160),
    unit: z.enum(PART_UNITS, { message: 'Choose a unit.' }),
    unit_cost: optionalUnitCost,
    is_critical: z.boolean(),
    minimum_stock: optionalQuantity,
    maximum_stock: optionalQuantity,
    reorder_quantity: optionalQuantity,
    default_location_id: z.string().nullable(),
    qr_code: optionalText(160),
    is_active: z.boolean(),
  })
  .superRefine((values, ctx) => {
    const minimum = numberOrNull(values.minimum_stock)
    const maximum = numberOrNull(values.maximum_stock)
    if (minimum !== null && maximum !== null && maximum < minimum) {
      ctx.addIssue({ code: 'custom', path: ['maximum_stock'], message: 'Maximum stock must be at least the minimum stock.' })
    }
  })
export type PartInput = z.infer<typeof PartInput>

export interface PartPayload {
  name: string
  sku: string | null
  description: string | null
  part_type_id: string | null
  manufacturer: string | null
  manufacturer_part_number: string | null
  unit: PartUnit
  is_critical: boolean
  minimum_stock: number | null
  maximum_stock: number | null
  reorder_quantity: number | null
  default_location_id: string | null
  qr_code: string | null
  is_active: boolean
  unit_cost?: number | null
}

/**
 * `unit_cost` is left out when the part already has ledger history: receipts
 * maintain it from then on and the server answers `unit_cost` with
 * `UNIT_COST_LOCKED` if it is sent.
 */
export function toPartPayload(values: PartInput, { includeUnitCost = true }: { includeUnitCost?: boolean } = {}): PartPayload {
  const payload: PartPayload = {
    name: values.name.trim(),
    sku: blankToNull(values.sku),
    description: blankToNull(values.description),
    part_type_id: values.part_type_id ?? null,
    manufacturer: blankToNull(values.manufacturer),
    manufacturer_part_number: blankToNull(values.manufacturer_part_number),
    unit: values.unit,
    is_critical: values.is_critical,
    minimum_stock: numberOrNull(values.minimum_stock),
    maximum_stock: numberOrNull(values.maximum_stock),
    reorder_quantity: numberOrNull(values.reorder_quantity),
    default_location_id: values.default_location_id ?? null,
    qr_code: blankToNull(values.qr_code),
    is_active: values.is_active,
  }
  if (includeUnitCost) payload.unit_cost = numberOrNull(values.unit_cost)
  return payload
}

export function partToInput(part: Partial<Part>): PartInput {
  const quantity = (value: number | null | undefined) => (value === null || value === undefined ? '' : String(value))
  return {
    name: part.name ?? '',
    sku: part.sku ?? '',
    description: part.description ?? '',
    part_type_id: part.part_type?.id ?? null,
    manufacturer: part.manufacturer ?? '',
    manufacturer_part_number: part.manufacturer_part_number ?? '',
    unit: ((PART_UNITS as readonly string[]).includes(part.unit ?? '') ? part.unit : 'each') as PartUnit,
    unit_cost: quantity(part.unit_cost),
    is_critical: Boolean(part.is_critical),
    minimum_stock: quantity(part.minimum_stock),
    maximum_stock: quantity(part.maximum_stock),
    reorder_quantity: quantity(part.reorder_quantity),
    default_location_id: part.default_location?.id ?? null,
    qr_code: part.qr_code ?? '',
    is_active: part.is_active ?? true,
  }
}

export const EMPTY_PART_INPUT: PartInput = {
  name: '',
  sku: '',
  description: '',
  part_type_id: null,
  manufacturer: '',
  manufacturer_part_number: '',
  unit: 'each',
  unit_cost: '',
  is_critical: false,
  minimum_stock: '',
  maximum_stock: '',
  reorder_quantity: '',
  default_location_id: null,
  qr_code: '',
  is_active: true,
}

/** `POST /part-types` (`services/parts.py::PART_TYPE_SPEC`). */
export const PartTypeInput = z.object({
  name: z.string().trim().min(1, 'Give the type a name.').max(120, 'Keep the name under 120 characters.'),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/, 'Pick a colour.'),
})
export type PartTypeInput = z.infer<typeof PartTypeInput>

/** `POST /parts/:id/transactions` (`services/inventory.py::TRANSACTION_SPEC` + its cross-field rules). */
export const MovementInput = z
  .object({
    type: z.enum(MOVEMENT_TYPES),
    location_id: z.string().nullable(),
    quantity: positiveQuantity('Enter a quantity.'),
    direction: z.enum(ADJUSTMENT_DIRECTIONS).nullable(),
    unit_cost: optionalUnitCost,
    work_order_id: z.string().nullable(),
    note: noteField,
  })
  .superRefine((values, ctx) => {
    if (values.type === 'adjustment' && !values.direction) {
      ctx.addIssue({ code: 'custom', path: ['direction'], message: 'Choose increase or decrease.' })
    }
    if (NOTE_REQUIRED_TYPES.includes(values.type) && !values.note?.trim()) {
      ctx.addIssue({ code: 'custom', path: ['note'], message: 'Say why the quantity changed.' })
    }
  })
export type MovementInput = z.infer<typeof MovementInput>

export interface MovementPayload {
  type: MovementType
  quantity: number
  location_id?: string
  direction?: AdjustmentDirection
  unit_cost?: number
  work_order_id?: string
  note?: string
}

/** Only the keys the type allows: the server rejects a unit cost on an issue and
 * a direction on anything but an adjustment. */
export function toMovementPayload(values: MovementInput): MovementPayload {
  const payload: MovementPayload = { type: values.type, quantity: Number(values.quantity) }
  if (values.location_id) payload.location_id = values.location_id
  if (values.type === 'adjustment' && values.direction) payload.direction = values.direction
  if (values.type === 'receipt' && values.unit_cost?.trim()) payload.unit_cost = Number(values.unit_cost)
  if (WORK_ORDER_TYPES.includes(values.type) && values.work_order_id) payload.work_order_id = values.work_order_id
  const note = values.note?.trim()
  if (note) payload.note = note
  return payload
}

/** `POST /inventory/transfers` (`services/inventory.py::TRANSFER_SPEC`). */
export const TransferInput = z
  .object({
    from_location_id: z.string().min(1, 'Choose where the stock is now.'),
    to_location_id: z.string().min(1, 'Choose where it is going.'),
    quantity: positiveQuantity('Enter a quantity.'),
    note: noteField,
  })
  .superRefine((values, ctx) => {
    if (values.from_location_id && values.from_location_id === values.to_location_id) {
      ctx.addIssue({ code: 'custom', path: ['to_location_id'], message: 'Choose a different location.' })
    }
  })
export type TransferInput = z.infer<typeof TransferInput>

export interface TransferPayload {
  part_id: string
  from_location_id: string
  to_location_id: string
  quantity: number
  note?: string
}

export function toTransferPayload(partId: string, values: TransferInput): TransferPayload {
  const payload: TransferPayload = {
    part_id: partId,
    from_location_id: values.from_location_id,
    to_location_id: values.to_location_id,
    quantity: Number(values.quantity),
  }
  const note = values.note?.trim()
  if (note) payload.note = note
  return payload
}

/** One-part cycle count (`services/inventory.py::CYCLE_COUNT_SPEC`). */
export const CountInput = z.object({
  location_id: z.string().min(1, 'Choose the location you counted.'),
  counted_quantity: quantityText('Enter what you counted.'),
  note: noteField,
})
export type CountInput = z.infer<typeof CountInput>

export interface CountPayload {
  location_id: string
  lines: Array<{ part_id: string; counted_quantity: number }>
  note?: string
}

export function toCountPayload(partId: string, values: CountInput): CountPayload {
  const payload: CountPayload = {
    location_id: values.location_id,
    lines: [{ part_id: partId, counted_quantity: Number(values.counted_quantity) }],
  }
  const note = values.note?.trim()
  if (note) payload.note = note
  return payload
}

/** `PUT /parts/:id/vendors` (`services/parts.py::VENDOR_LINK_SPEC`, replace semantics). */
export const VendorLinkInput = z.object({
  vendor_id: z.string().min(1, 'Choose a vendor.'),
  vendor_part_number: optionalText(160),
  url: z
    .string()
    .trim()
    .max(500, 'Keep the link under 500 characters.')
    .optional()
    .or(z.literal(''))
    .refine((value) => !value || WEBSITE_RE.test(value), 'Start the link with http:// or https://.'),
  preferred: z.boolean(),
  last_price: optionalUnitCost,
})
export type VendorLinkInput = z.infer<typeof VendorLinkInput>

export const VendorLinksInput = z
  .object({ vendors: z.array(VendorLinkInput).max(MAX_VENDOR_LINKS, `At most ${MAX_VENDOR_LINKS} vendors.`) })
  .superRefine((values, ctx) => {
    const seen = new Map<string, number>()
    values.vendors.forEach((entry, index) => {
      if (seen.has(entry.vendor_id)) ctx.addIssue({ code: 'custom', path: ['vendors', index, 'vendor_id'], message: 'This vendor is already listed.' })
      else seen.set(entry.vendor_id, index)
    })
    const preferred = values.vendors.map((entry, index) => (entry.preferred ? index : -1)).filter((index) => index >= 0)
    for (const index of preferred.slice(1)) {
      ctx.addIssue({ code: 'custom', path: ['vendors', index, 'preferred'], message: 'Only one vendor can be preferred.' })
    }
  })
export type VendorLinksInput = z.infer<typeof VendorLinksInput>

export interface VendorLinkPayload {
  vendor_id: string
  vendor_part_number: string | null
  url: string | null
  preferred: boolean
  last_price: number | null
}

export function toVendorLinksPayload(values: VendorLinksInput): { vendors: VendorLinkPayload[] } {
  return {
    vendors: values.vendors.map((entry) => ({
      vendor_id: entry.vendor_id,
      vendor_part_number: blankToNull(entry.vendor_part_number),
      url: blankToNull(entry.url),
      preferred: entry.preferred,
      last_price: numberOrNull(entry.last_price),
    })),
  }
}

export function vendorLinksToInput(links: PartVendorLink[]): VendorLinksInput {
  return {
    vendors: links.map((link) => ({
      vendor_id: link.vendor.id,
      vendor_part_number: link.vendor_part_number ?? '',
      url: link.url ?? '',
      preferred: Boolean(link.preferred),
      last_price: link.last_price === null || link.last_price === undefined ? '' : String(link.last_price),
    })),
  }
}

/** `PUT /parts/:id/assets` (`services/parts.py::ASSET_LINKS_SPEC`). */
export const AssetLinksInput = z.object({
  asset_ids: z.array(z.string()).max(MAX_ASSET_LINKS, `At most ${MAX_ASSET_LINKS} assets.`),
})
export type AssetLinksInput = z.infer<typeof AssetLinksInput>

/* List parameters ---------------------------------------------------------------- */

export const PART_SORTS = ['name', '-name', 'sku', '-sku', 'available', '-available', 'updated_at', '-updated_at'] as const
export type PartSort = (typeof PART_SORTS)[number]

export const DEFAULT_PART_SORT: PartSort = 'name'

export interface PartListParams {
  q?: string
  type?: string[]
  location?: string[]
  vendor?: string[]
  asset?: string[]
  stock?: string[]
  critical?: 'true' | 'false'
  active?: 'true' | 'false' | 'all'
  sort?: string
  limit?: number
}

export interface PartTransactionParams {
  type?: string[]
  location?: string[]
  limit?: number
}
