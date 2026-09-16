/**
 * Purchase requests (`asme/ops/serializers/purchase_requests.py` and
 * `asme/ops/services/purchase_requests.py`).
 *
 * The API shapes mirror `purchase_request` / `purchase_request_detail`; the
 * `*Input` schemas are what the forms hold (strings, because number inputs give
 * strings) and the `to*Payload` helpers turn them into the JSON bodies. Line
 * totals are computed with the same rule the server uses - quantity times unit
 * price rounded half-up to cents - so the number on screen and the number that
 * comes back cannot drift.
 */

import { z } from 'zod'
import { LocationRef, ProjectRef, UserRef, VendorRef, listOf } from './common'

/* Enumerations ----------------------------------------------------------------- */

export const PURCHASE_REQUEST_STATUSES = [
  'draft',
  'submitted',
  'treasurer_review',
  'advisor_review',
  'approved',
  'ordered',
  'partially_received',
  'received',
  'declined',
  'canceled',
] as const
export type PurchaseRequestStatus = (typeof PURCHASE_REQUEST_STATUSES)[number]

export const PURCHASE_REQUEST_STATUS_LABELS: Record<PurchaseRequestStatus, string> = {
  draft: 'Draft',
  submitted: 'Project lead review',
  treasurer_review: 'Treasurer review',
  advisor_review: 'Advisor review',
  approved: 'Approved',
  ordered: 'Ordered',
  partially_received: 'Partially received',
  received: 'Received',
  declined: 'Declined',
  canceled: 'Canceled',
}

/** Statuses the server treats as closed (`PURCHASE_REQUEST_CLOSED_STATUSES`). */
export const PURCHASE_REQUEST_CLOSED_STATUSES: readonly string[] = ['received', 'declined', 'canceled']

export function purchaseRequestStatusLabel(status: string | null | undefined): string {
  if (!status) return '—'
  return PURCHASE_REQUEST_STATUS_LABELS[status as PurchaseRequestStatus] ?? status.replace(/_/g, ' ')
}

/** `available_actions` values, in the order the server returns them. */
export const PURCHASE_REQUEST_ACTIONS = ['submit', 'approve', 'decline', 'request_changes', 'order', 'receive', 'cancel', 'reopen'] as const
export type PurchaseRequestAction = (typeof PURCHASE_REQUEST_ACTIONS)[number]

/** The route spelling of each action (`request_changes` posts to `request-changes`). */
export const PURCHASE_REQUEST_ACTION_PATHS: Record<PurchaseRequestAction, string> = {
  submit: 'submit',
  approve: 'approve',
  decline: 'decline',
  request_changes: 'request-changes',
  order: 'order',
  receive: 'receive',
  cancel: 'cancel',
  reopen: 'reopen',
}

export const PURCHASE_REQUEST_ACTION_LABELS: Record<PurchaseRequestAction, string> = {
  submit: 'Submit for approval',
  approve: 'Approve',
  decline: 'Decline',
  request_changes: 'Request changes',
  order: 'Mark as ordered',
  receive: 'Receive items',
  cancel: 'Cancel request',
  reopen: 'Reopen as draft',
}

export function isPurchaseRequestAction(value: string): value is PurchaseRequestAction {
  return (PURCHASE_REQUEST_ACTIONS as readonly string[]).includes(value)
}

export const PURCHASE_REQUEST_TABS = ['mine', 'review', 'open', 'closed'] as const
export type PurchaseRequestTab = (typeof PURCHASE_REQUEST_TABS)[number]
export const DEFAULT_PURCHASE_REQUEST_TAB: PurchaseRequestTab = 'mine'

export const PURCHASE_REQUEST_SORTS = ['-updated_at', '-created_at', 'needed_by', '-estimated_total', 'number'] as const
export type PurchaseRequestSort = (typeof PURCHASE_REQUEST_SORTS)[number]
export const DEFAULT_PURCHASE_REQUEST_SORT: PurchaseRequestSort = '-updated_at'

export const PURCHASE_REQUEST_SORT_OPTIONS: Array<{ value: PurchaseRequestSort; label: string }> = [
  { value: '-updated_at', label: 'Recently updated' },
  { value: '-created_at', label: 'Newest first' },
  { value: 'needed_by', label: 'Needed by (soonest)' },
  { value: '-estimated_total', label: 'Largest total' },
  { value: 'number', label: 'Request number' },
]

export const MAX_PURCHASE_REQUEST_ITEMS = 100

/* API shapes -------------------------------------------------------------------- */

export const PurchaseRequestRef = z.looseObject({
  id: z.string(),
  number: z.number(),
  display_number: z.string(),
  title: z.string(),
  status: z.string(),
})
export type PurchaseRequestRef = z.infer<typeof PurchaseRequestRef>

/** The `part_ref` carried on a line item. */
export const LinePartRef = z.looseObject({
  id: z.string(),
  name: z.string(),
  sku: z.string().nullable().optional(),
  unit: z.string().default('each'),
})
export type LinePartRef = z.infer<typeof LinePartRef>

export const PurchaseRequest = PurchaseRequestRef.extend({
  requester: UserRef.nullable().optional(),
  project: ProjectRef.nullable().optional(),
  vendor: VendorRef.nullable().optional(),
  needed_by: z.string().nullable().optional(),
  purpose: z.string().nullable().optional(),
  budget_code: z.string().nullable().optional(),
  shipping_amount: z.number().nullable().default(0),
  tax_amount: z.number().nullable().default(0),
  estimated_total: z.number().nullable().default(0),
  approved_total: z.number().nullable().optional(),
  item_count: z.number().default(0),
  order_reference: z.string().nullable().optional(),
  submitted_at: z.string().nullable().optional(),
  approved_at: z.string().nullable().optional(),
  ordered_at: z.string().nullable().optional(),
  received_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  is_overdue: z.boolean().default(false),
})
export type PurchaseRequest = z.infer<typeof PurchaseRequest>

export const PurchaseRequestTabCounts = z.object({
  mine: z.number().default(0),
  review: z.number().default(0),
  open: z.number().default(0),
  closed: z.number().default(0),
  all: z.number().default(0),
})
export type PurchaseRequestTabCounts = z.infer<typeof PurchaseRequestTabCounts>

export const PurchaseRequestList = listOf(PurchaseRequest).extend({ tabs: PurchaseRequestTabCounts.optional() })
export type PurchaseRequestList = z.infer<typeof PurchaseRequestList>

export const PurchaseRequestItem = z.looseObject({
  id: z.string(),
  part: LinePartRef.nullable().optional(),
  description: z.string(),
  vendor_part_number: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  quantity: z.number().default(0),
  unit_price: z.number().nullable().default(0),
  line_total: z.number().nullable().default(0),
  received_quantity: z.number().nullable().default(0),
  receive_location: LocationRef.nullable().optional(),
})
export type PurchaseRequestItem = z.infer<typeof PurchaseRequestItem>

export const PurchaseRequestEvent = z.looseObject({
  id: z.string(),
  action: z.string(),
  from_status: z.string().nullable().optional(),
  to_status: z.string(),
  step: z.string().nullable().optional(),
  comment: z.string().nullable().optional(),
  actor: UserRef.nullable().optional(),
  created_at: z.string().nullable().optional(),
})
export type PurchaseRequestEvent = z.infer<typeof PurchaseRequestEvent>

export const PurchaseRequestDetail = PurchaseRequest.extend({
  items: z.array(PurchaseRequestItem).default([]),
  events: z.array(PurchaseRequestEvent).default([]),
  decline_reason: z.string().nullable().optional(),
  attachment_count: z.number().default(0),
  available_actions: z.array(z.string()).default([]),
})
export type PurchaseRequestDetail = z.infer<typeof PurchaseRequestDetail>

/** `GET /purchasing/settings` → `{ purchasing: … }`. */
export const PurchasingSettings = z.object({
  advisor_review_threshold: z.number().nullable().default(null),
  require_project_lead_approval: z.boolean().default(false),
  critical_parts_team_id: z.string().nullable().default(null),
})
export type PurchasingSettings = z.infer<typeof PurchasingSettings>

/** The handful of `GET /parts` fields the line-item picker needs. */
export const PartPickerItem = z.looseObject({
  id: z.string(),
  name: z.string(),
  sku: z.string().nullable().optional(),
  unit: z.string().default('each'),
  description: z.string().nullable().optional(),
  manufacturer_part_number: z.string().nullable().optional(),
  unit_cost: z.number().nullable().optional(),
  default_location: LocationRef.nullable().optional(),
  preferred_vendor: VendorRef.nullable().optional(),
})
export type PartPickerItem = z.infer<typeof PartPickerItem>

export const PartPickerList = listOf(PartPickerItem)
export type PartPickerList = z.infer<typeof PartPickerList>

/* Numbers ----------------------------------------------------------------------- */

const QUANTITY_PATTERN = /^\d+(\.\d{1,3})?$/
const UNIT_PRICE_PATTERN = /^\d+(\.\d{1,4})?$/
const MONEY_PATTERN = /^\d+(\.\d{1,2})?$/
const QUANTITY_MESSAGE = 'Enter a quantity like 2 or 0.5, with at most three decimals.'
const UNIT_PRICE_MESSAGE = 'Enter a price like 12.50, with at most four decimals.'
const MONEY_MESSAGE = 'Enter an amount like 18.95.'

/**
 * A decimal value as an exact integer count of `10 ** scale` units.
 *
 * The server does this arithmetic in `Decimal`; doing it on doubles rounds a
 * product that lands exactly on half a cent the wrong way (3 x 1.005 is
 * 3.014999999999999 as a double, so half-up gives 3.01 where the server stores
 * 3.02), and the total on screen then disagrees with the stored
 * `estimated_total` the advisor threshold is compared against.
 */
interface Decimals {
  units: bigint
  scale: number
}

const DECIMAL_PATTERN = /^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/

function decimals(value: number | string | null | undefined): Decimals {
  const text = (value ?? '').toString().trim()
  if (!text) return { units: 0n, scale: 0 }
  const match = DECIMAL_PATTERN.exec(text)
  if (!match) return { units: 0n, scale: 0 }
  const [, sign, whole = '', fraction = '', exponent] = match
  const digits = `${whole}${fraction}`
  if (!digits) return { units: 0n, scale: 0 }
  let units = BigInt(digits)
  let scale = fraction.length - Number(exponent ?? 0)
  while (scale < 0) {
    units *= 10n
    scale += 1
  }
  return { units: sign === '-' ? -units : units, scale }
}

/** Rescale to `places`, rounding half away from zero exactly as `ROUND_HALF_UP` does. */
function quantize({ units, scale }: Decimals, places: number): bigint {
  if (scale === places) return units
  if (scale < places) return units * 10n ** BigInt(places - scale)
  const divisor = 10n ** BigInt(scale - places)
  const negative = units < 0n
  const magnitude = negative ? -units : units
  const whole = magnitude / divisor
  const rounded = (magnitude % divisor) * 2n >= divisor ? whole + 1n : whole
  return negative ? -rounded : rounded
}

function roundDecimal(value: number | string | null | undefined, places: number): number {
  if (typeof value === 'number' && !Number.isFinite(value)) return 0
  return Number(quantize(decimals(value), places)) / 10 ** places
}

/** Half-up to cents, the rule `serializers/purchase_requests.line_total` uses. */
export function roundMoney(value: number): number {
  return roundDecimal(value, 2)
}

/** Half-up to four places, the precision of the `Numeric(12, 4)` unit-price column. */
export function roundUnitCost(value: number): number {
  return roundDecimal(value, 4)
}

export function lineTotal(quantity: number | string | null | undefined, unitPrice: number | string | null | undefined): number {
  const q = decimals(quantity)
  const p = decimals(unitPrice)
  return Number(quantize({ units: q.units * p.units, scale: q.scale + p.scale }, 2)) / 100
}

export function toNumber(value: number | string | null | undefined): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const text = (value ?? '').toString().trim()
  if (!text) return 0
  const parsed = Number(text)
  return Number.isFinite(parsed) ? parsed : 0
}

export interface PurchaseRequestTotals {
  subtotal: number
  shipping: number
  tax: number
  total: number
}

/** `estimated_total = sum(line_total) + shipping + tax`. */
export function totalsFor(lines: Array<{ quantity?: unknown; unit_price?: unknown }>, shipping: unknown, tax: unknown): PurchaseRequestTotals {
  const subtotal = roundMoney(lines.reduce((sum, line) => sum + lineTotal(line.quantity as string, line.unit_price as string), 0))
  const shippingAmount = roundMoney(toNumber(shipping as string))
  const taxAmount = roundMoney(toNumber(tax as string))
  return { subtotal, shipping: shippingAmount, tax: taxAmount, total: roundMoney(subtotal + shippingAmount + taxAmount) }
}

/** Quantity still to receive on a line. */
export function outstandingQuantity(item: Pick<PurchaseRequestItem, 'quantity' | 'received_quantity'>): number {
  const outstanding = toNumber(item.quantity) - toNumber(item.received_quantity)
  return outstanding > 0 ? Math.round(outstanding * 1000) / 1000 : 0
}

/* Form schemas ------------------------------------------------------------------- */

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `Keep this under ${max} characters.`)
    .optional()
    .or(z.literal(''))

const optionalUrl = z
  .string()
  .trim()
  .regex(/^$|^https?:\/\/\S+$/i, 'Start the link with http:// or https://.')
  .max(500, 'Keep the link under 500 characters.')
  .optional()
  .or(z.literal(''))

const optionalMoney = z
  .string()
  .trim()
  .regex(new RegExp(`^$|${MONEY_PATTERN.source}`), MONEY_MESSAGE)
  .optional()
  .or(z.literal(''))

const optionalComment = z.string().trim().max(4000, 'Keep the comment under 4000 characters.').optional().or(z.literal(''))

const requiredComment = z.string().trim().min(1, 'A comment is required.').max(4000, 'Keep the comment under 4000 characters.')

/** One editable line. `key` is a client-side id so React keys survive reordering. */
export const PurchaseRequestLineInput = z.object({
  key: z.string(),
  part_id: z.string().nullable(),
  description: z.string().trim().min(1, 'Describe what to buy.').max(300, 'Keep the description under 300 characters.'),
  vendor_part_number: optionalText(160),
  url: optionalUrl,
  quantity: z
    .string()
    .trim()
    .min(1, 'Enter a quantity.')
    .regex(QUANTITY_PATTERN, QUANTITY_MESSAGE)
    .refine((value) => Number(value) > 0, 'Enter a quantity greater than zero.'),
  unit_price: z
    .string()
    .trim()
    .regex(new RegExp(`^$|${UNIT_PRICE_PATTERN.source}`), UNIT_PRICE_MESSAGE)
    .optional()
    .or(z.literal('')),
  receive_location_id: z.string().nullable(),
})
export type PurchaseRequestLineInput = z.infer<typeof PurchaseRequestLineInput>

export const PurchaseRequestInput = z.object({
  title: z.string().trim().min(1, 'Give the request a title.').max(200, 'Keep the title under 200 characters.'),
  project_id: z.string().nullable(),
  vendor_id: z.string().nullable(),
  needed_by: z
    .string()
    .regex(/^(\d{4}-\d{2}-\d{2})?$/, 'Enter a date as YYYY-MM-DD.')
    .optional()
    .or(z.literal('')),
  purpose: z.string().trim().max(4000, 'Keep the purpose under 4000 characters.').optional().or(z.literal('')),
  budget_code: optionalText(60),
  shipping_amount: optionalMoney,
  tax_amount: optionalMoney,
  items: z
    .array(PurchaseRequestLineInput)
    .min(1, 'Add at least one line item.')
    .max(MAX_PURCHASE_REQUEST_ITEMS, `A purchase request can hold at most ${MAX_PURCHASE_REQUEST_ITEMS} line items.`),
})
export type PurchaseRequestInput = z.infer<typeof PurchaseRequestInput>

export interface PurchaseRequestLinePayload {
  part_id: string | null
  description: string
  vendor_part_number: string | null
  url: string | null
  quantity: number
  unit_price: number
  receive_location_id: string | null
}

export interface PurchaseRequestPayload {
  title: string
  project_id: string | null
  vendor_id: string | null
  needed_by: string | null
  purpose: string | null
  budget_code: string | null
  shipping_amount: number
  tax_amount: number
  items: PurchaseRequestLinePayload[]
}

const blankToNull = (value: string | null | undefined): string | null => {
  const text = (value ?? '').trim()
  return text ? text : null
}

export function toPurchaseRequestPayload(values: PurchaseRequestInput): PurchaseRequestPayload {
  return {
    title: values.title.trim(),
    project_id: values.project_id ?? null,
    vendor_id: values.vendor_id ?? null,
    needed_by: blankToNull(values.needed_by),
    purpose: blankToNull(values.purpose),
    budget_code: blankToNull(values.budget_code),
    shipping_amount: roundMoney(toNumber(values.shipping_amount)),
    tax_amount: roundMoney(toNumber(values.tax_amount)),
    items: values.items.map((line) => ({
      part_id: line.part_id ?? null,
      description: line.description.trim(),
      vendor_part_number: blankToNull(line.vendor_part_number),
      url: blankToNull(line.url),
      quantity: toNumber(line.quantity),
      // `unit_price` is Numeric(12, 4): rounding it to cents here would silently
      // reprice a sub-cent quote (0.0525 becoming 0.05) before it is ever stored.
      unit_price: roundUnitCost(toNumber(line.unit_price)),
      receive_location_id: line.receive_location_id ?? null,
    })),
  }
}

/** Form values for an existing draft. */
export function purchaseRequestFormValues(request: PurchaseRequestDetail | null | undefined): PurchaseRequestInput {
  return {
    title: request?.title ?? '',
    project_id: request?.project?.id ?? null,
    vendor_id: request?.vendor?.id ?? null,
    needed_by: request?.needed_by ?? '',
    purpose: request?.purpose ?? '',
    budget_code: request?.budget_code ?? '',
    shipping_amount: amountText(request?.shipping_amount),
    tax_amount: amountText(request?.tax_amount),
    items: (request?.items ?? []).map((item, index) => ({
      key: `${item.id}-${index}`,
      part_id: item.part?.id ?? null,
      description: item.description,
      vendor_part_number: item.vendor_part_number ?? '',
      url: item.url ?? '',
      quantity: quantityText(item.quantity),
      unit_price: amountText(item.unit_price),
      receive_location_id: item.receive_location?.id ?? null,
    })),
  }
}

export function blankLine(key: string): PurchaseRequestLineInput {
  return { key, part_id: null, description: '', vendor_part_number: '', url: '', quantity: '1', unit_price: '', receive_location_id: null }
}

function amountText(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return ''
  return String(value)
}

function quantityText(value: number | null | undefined): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

/* Action payloads ----------------------------------------------------------------- */

export const ApproveInput = z.object({ comment: optionalComment, approved_total: optionalMoney })
export type ApproveInput = z.infer<typeof ApproveInput>

export interface ApprovePayload {
  comment?: string
  approved_total?: number
}

export function toApprovePayload(values: ApproveInput): ApprovePayload {
  const payload: ApprovePayload = {}
  const comment = blankToNull(values.comment)
  if (comment) payload.comment = comment
  const total = blankToNull(values.approved_total)
  if (total !== null) payload.approved_total = roundMoney(toNumber(total))
  return payload
}

/** `decline` and `request-changes` both need a comment. */
export const CommentActionInput = z.object({ comment: requiredComment })
export type CommentActionInput = z.infer<typeof CommentActionInput>

/** `cancel` takes an optional comment. */
export const CancelInput = z.object({ comment: optionalComment })
export type CancelInput = z.infer<typeof CancelInput>

export const OrderInput = z.object({
  order_reference: optionalText(120),
  ordered_at: z.string().optional().or(z.literal('')),
  approved_total: optionalMoney,
  comment: optionalComment,
})
export type OrderInput = z.infer<typeof OrderInput>

export interface OrderPayload {
  order_reference?: string
  ordered_at?: string
  approved_total?: number
  comment?: string
}

export function toOrderPayload(values: OrderInput, isoOrderedAt: string | null): OrderPayload {
  const payload: OrderPayload = {}
  const reference = blankToNull(values.order_reference)
  if (reference) payload.order_reference = reference
  if (isoOrderedAt) payload.ordered_at = isoOrderedAt
  const total = blankToNull(values.approved_total)
  if (total !== null) payload.approved_total = roundMoney(toNumber(total))
  const comment = blankToNull(values.comment)
  if (comment) payload.comment = comment
  return payload
}

export interface ReceiveLinePayload {
  item_id: string
  quantity: number
  location_id?: string
}

export interface ReceivePayload {
  lines: ReceiveLinePayload[]
  note?: string
}

/** The receive form's values, inferred from the schema `receiveSchema` builds. */
export type ReceiveValues = z.infer<ReturnType<typeof receiveSchema>>

/**
 * Receiving is validated against the outstanding quantity of each line, so the
 * schema is built from the request's own items. Lines left blank are skipped;
 * at least one must carry a quantity.
 */
export function receiveSchema(items: PurchaseRequestItem[]) {
  const outstanding = new Map(items.map((item) => [item.id, outstandingQuantity(item)]))
  return z
    .object({
      lines: z.array(
        z.object({
          item_id: z.string(),
          quantity: z
            .string()
            .trim()
            .regex(new RegExp(`^$|${QUANTITY_PATTERN.source}`), QUANTITY_MESSAGE)
            .optional()
            .or(z.literal('')),
          location_id: z.string().nullable(),
        }),
      ),
      note: optionalComment,
    })
    .superRefine((values, ctx) => {
      let received = 0
      values.lines.forEach((line, index) => {
        const text = (line.quantity ?? '').trim()
        if (!text) return
        const quantity = Number(text)
        const max = outstanding.get(line.item_id) ?? 0
        if (quantity <= 0) {
          ctx.addIssue({ code: 'custom', path: ['lines', index, 'quantity'], message: 'Enter a quantity greater than zero.' })
          return
        }
        if (quantity > max) {
          ctx.addIssue({ code: 'custom', path: ['lines', index, 'quantity'], message: `At most ${max} outstanding on this line.` })
          return
        }
        received += 1
      })
      if (received === 0) {
        ctx.addIssue({ code: 'custom', path: ['lines'], message: 'Enter a quantity on at least one line.' })
      }
    })
}

export function toReceivePayload(values: ReceiveValues): ReceivePayload {
  const payload: ReceivePayload = {
    lines: values.lines
      .filter((line) => (line.quantity ?? '').trim() !== '')
      .map((line) => {
        const entry: ReceiveLinePayload = { item_id: line.item_id, quantity: toNumber(line.quantity) }
        if (line.location_id) entry.location_id = line.location_id
        return entry
      }),
  }
  const note = blankToNull(values.note)
  if (note) payload.note = note
  return payload
}

export const PurchasingSettingsInput = z.object({
  advisor_review_threshold: optionalMoney,
  require_project_lead_approval: z.boolean(),
  critical_parts_team_id: z.string().nullable(),
})
export type PurchasingSettingsInput = z.infer<typeof PurchasingSettingsInput>

export interface PurchasingSettingsPayload {
  advisor_review_threshold: number | null
  require_project_lead_approval: boolean
  critical_parts_team_id: string | null
}

/** PUT replaces the whole block, so every key is always sent. */
export function toPurchasingSettingsPayload(values: PurchasingSettingsInput): PurchasingSettingsPayload {
  const threshold = blankToNull(values.advisor_review_threshold)
  return {
    advisor_review_threshold: threshold === null ? null : roundMoney(toNumber(threshold)),
    require_project_lead_approval: values.require_project_lead_approval,
    critical_parts_team_id: values.critical_parts_team_id ?? null,
  }
}

export function purchasingSettingsFormValues(settings: PurchasingSettings | null | undefined): PurchasingSettingsInput {
  return {
    advisor_review_threshold: settings?.advisor_review_threshold === null || settings?.advisor_review_threshold === undefined ? '' : String(settings.advisor_review_threshold),
    require_project_lead_approval: settings?.require_project_lead_approval ?? false,
    critical_parts_team_id: settings?.critical_parts_team_id ?? null,
  }
}

/* List parameters ------------------------------------------------------------------ */

export interface PurchaseRequestListParams {
  q?: string
  tab?: PurchaseRequestTab | 'all'
  sort?: PurchaseRequestSort
  status?: string[]
  project?: string[]
  vendor?: string[]
  requester?: string[]
  limit?: number
}

/**
 * The server keys validation errors on line items as `items[2].quantity`;
 * React Hook Form addresses the same field as `items.2.quantity`.
 */
export function toFormPath(field: string): string {
  return field.replace(/\[(\d+)\]/g, '.$1')
}
