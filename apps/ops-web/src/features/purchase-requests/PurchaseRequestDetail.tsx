/**
 * The right-hand pane of the Purchase Requests screen: header with the number,
 * status and totals, the line items, the request's own fields and the approval
 * timeline built from the server's `events`. Every control the pane offers comes
 * from `available_actions`, so it stays in step with the workflow.
 */

import { ExternalLink, ShoppingCart } from 'lucide-react'
import type { ReactNode } from 'react'
import { PURCHASE_REQUEST_ACTIONS, type PurchaseRequestDetail as PurchaseRequestDetailShape, type PurchaseRequestEvent, type PurchaseRequestItem } from '@/api/contracts/purchaseRequests'
import { formatDate, formatMoney } from '@/lib/dates'
import { ActivityTimeline, Card, DetailPanel, FieldList, InlineAlert, Stack, type TimelineItem } from '@/ui'
import { Money, NeededBy, PurchaseRequestStatusBadge } from './bits'
import { PurchaseRequestActions } from './PurchaseRequestActions'
import styles from './purchase-requests.module.css'

const EVENT_LABELS: Record<string, string> = {
  submit: 'Submitted for approval',
  approve: 'Approved',
  decline: 'Declined',
  request_changes: 'Changes requested',
  order: 'Marked as ordered',
  receive: 'Items received',
  cancel: 'Canceled',
  reopen: 'Reopened as a draft',
}

const STEP_LABELS: Record<string, string> = {
  project_lead: 'Project lead',
  treasurer: 'Treasurer',
  advisor: 'Faculty advisor',
}

function eventTitle(event: PurchaseRequestEvent): string {
  const base = EVENT_LABELS[event.action] ?? event.action.replace(/_/g, ' ')
  const step = event.step ? STEP_LABELS[event.step] ?? event.step : null
  return step ? `${base} · ${step}` : base
}

function timelineItems(events: PurchaseRequestEvent[]): TimelineItem[] {
  return events.map((event) => ({
    id: event.id,
    title: (
      <span className={styles.titleRow}>
        {eventTitle(event)}
        <PurchaseRequestStatusBadge status={event.to_status} size="sm" />
      </span>
    ),
    actor: event.actor?.name ?? null,
    at: event.created_at ?? '',
    content: event.comment ? <p className={styles.timelineComment}>{event.comment}</p> : undefined,
  }))
}

export interface PurchaseRequestDetailProps {
  request: PurchaseRequestDetailShape
  canEdit: boolean
  onEdit: () => void
}

export function PurchaseRequestDetail({ request, canEdit, onEdit }: PurchaseRequestDetailProps) {
  const itemsTotal = request.items.reduce((sum, item) => sum + (item.line_total ?? 0), 0)
  const hasActions = request.available_actions.some((action) => (PURCHASE_REQUEST_ACTIONS as readonly string[]).includes(action))

  return (
    <DetailPanel
      eyebrow={
        <span className={styles.eyebrow}>
          <ShoppingCart size={12} aria-hidden="true" />
          {request.display_number}
        </span>
      }
      title={
        <span className={styles.titleRow}>
          {request.title}
          <PurchaseRequestStatusBadge status={request.status} />
        </span>
      }
      subtitle={[request.requester?.name, request.project?.name, request.vendor?.name].filter(Boolean).join(' · ') || undefined}
      actions={hasActions || canEdit ? <PurchaseRequestActions request={request} canEdit={canEdit} onEdit={onEdit} /> : undefined}
    >
      <Stack>
        {request.status === 'declined' && request.decline_reason && (
          <InlineAlert tone="danger" title="Declined">
            {request.decline_reason}
          </InlineAlert>
        )}

        <Card title="Totals">
          <div className={styles.totals}>
            <Total label="Estimated" value={formatMoney(request.estimated_total ?? 0)} />
            <Total label="Approved" value={request.approved_total === null || request.approved_total === undefined ? '—' : formatMoney(request.approved_total)} />
            <Total label="Line items" value={String(request.items.length || request.item_count)} />
            <Total label="Needed by" value={<NeededBy date={request.needed_by} overdue={request.is_overdue} />} />
          </div>
        </Card>

        <Card title="Line items" flush>
          {request.items.length === 0 ? (
            <p className={`${styles.padded} ${styles.muted}`}>No line items yet.</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption className="sr-only">Line items on {request.display_number}</caption>
                <thead>
                  <tr>
                    <th scope="col">Item</th>
                    <th scope="col" className={styles.numeric}>
                      Qty
                    </th>
                    <th scope="col" className={styles.numeric}>
                      Unit price
                    </th>
                    <th scope="col" className={styles.numeric}>
                      Line total
                    </th>
                    <th scope="col" className={styles.numeric}>
                      Received
                    </th>
                    <th scope="col">Receive at</th>
                  </tr>
                </thead>
                <tbody>
                  {request.items.map((item) => (
                    <LineRow key={item.id} item={item} />
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={3}>Items</td>
                    <td className={styles.numeric}>{formatMoney(itemsTotal)}</td>
                    <td colSpan={2} />
                  </tr>
                  <tr>
                    <td colSpan={3}>Shipping</td>
                    <td className={styles.numeric}>{formatMoney(request.shipping_amount ?? 0)}</td>
                    <td colSpan={2} />
                  </tr>
                  <tr>
                    <td colSpan={3}>Tax</td>
                    <td className={styles.numeric}>{formatMoney(request.tax_amount ?? 0)}</td>
                    <td colSpan={2} />
                  </tr>
                  <tr>
                    <td colSpan={3}>Estimated total</td>
                    <td className={styles.numeric}>
                      <strong>{formatMoney(request.estimated_total ?? 0)}</strong>
                    </td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </Card>

        <Card title="Request">
          <FieldList
            items={[
              { label: 'Requester', value: request.requester?.name ?? '—' },
              { label: 'Project', value: request.project ? `${request.project.name} (${request.project.code})` : '—' },
              { label: 'Vendor', value: request.vendor?.name ?? '—' },
              { label: 'Status', value: <PurchaseRequestStatusBadge status={request.status} /> },
              { label: 'Needed by', value: <NeededBy date={request.needed_by} overdue={request.is_overdue} /> },
              { label: 'Budget code', value: request.budget_code || '—' },
              { label: 'Order reference', value: request.order_reference || '—' },
              { label: 'Submitted', value: request.submitted_at ? formatDate(request.submitted_at) : '—' },
              { label: 'Approved', value: request.approved_at ? formatDate(request.approved_at) : '—' },
              { label: 'Ordered', value: request.ordered_at ? formatDate(request.ordered_at) : '—' },
              { label: 'Received', value: request.received_at ? formatDate(request.received_at) : '—' },
              { label: 'Purpose', value: request.purpose ? <p className={styles.timelineComment}>{request.purpose}</p> : '—' },
            ]}
          />
        </Card>

        <Card title="Approval timeline">
          <ActivityTimeline items={timelineItems(request.events)} emptyText="Nothing has happened yet. Submitting this request starts the timeline." />
        </Card>
      </Stack>
    </DetailPanel>
  )
}

function Total({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className={styles.total}>
      <span className={styles.totalLabel}>{label}</span>
      <span className={styles.totalValue}>{value}</span>
    </div>
  )
}

function LineRow({ item }: { item: PurchaseRequestItem }) {
  const meta = [item.part?.sku, item.vendor_part_number].filter(Boolean).join(' · ')
  return (
    <tr>
      <td className={styles.wrap}>
        <span className={styles.lineDescription}>
          <span>{item.description}</span>
          {meta && <span className={styles.lineMeta}>{meta}</span>}
          {item.url && (
            <a href={item.url} target="_blank" rel="noopener noreferrer" className={styles.lineMeta}>
              Product link
              <ExternalLink size={11} aria-hidden="true" />
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          )}
        </span>
      </td>
      <td className={styles.numeric}>
        {item.quantity}
        {item.part?.unit ? ` ${item.part.unit}` : ''}
      </td>
      <td className={styles.numeric}>
        <Money value={item.unit_price} />
      </td>
      <td className={styles.numeric}>
        <Money value={item.line_total} />
      </td>
      <td className={styles.numeric}>{item.received_quantity ?? 0}</td>
      <td>{item.receive_location?.name ?? <span className={styles.muted}>Default</span>}</td>
    </tr>
  )
}
