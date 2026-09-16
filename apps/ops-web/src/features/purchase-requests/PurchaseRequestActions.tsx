/**
 * The action bar on a purchase request and the dialogs behind it.
 *
 * Which buttons exist is decided entirely by `available_actions` from the API -
 * the screen never re-derives the workflow rules - so a request the caller may
 * not act on simply shows no buttons. `submit` and `reopen` post straight away;
 * everything else opens a dialog because it carries a comment, a total, an
 * order reference or per-line receipt quantities.
 */

import { zodResolver } from '@hookform/resolvers/zod'
import { Check, CircleSlash, PackageCheck, RotateCcw, Send, ShoppingCart, Undo2, X } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useFieldArray, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  ApproveInput,
  CancelInput,
  CommentActionInput,
  OrderInput,
  PURCHASE_REQUEST_ACTION_LABELS,
  isPurchaseRequestAction,
  outstandingQuantity,
  receiveSchema,
  toApprovePayload,
  toFormPath,
  toOrderPayload,
  toReceivePayload,
  type ApproveInput as ApproveValues,
  type CancelInput as CancelValues,
  type CommentActionInput as CommentValues,
  type OrderInput as OrderValues,
  type PurchaseRequestAction,
  type PurchaseRequestDetail,
  type ReceiveValues,
} from '@/api/contracts/purchaseRequests'
import { useLocations } from '@/api/queries/locations'
import { usePurchaseRequestAction } from '@/api/queries/purchaseRequests'
import { formatMoney, fromDateTimeLocal } from '@/lib/dates'
import { Button, Combobox, DateTimeInput, Dialog, FormField, InlineAlert, Input, Textarea, useToast } from '@/ui'
import { money } from './bits'
import styles from './purchase-requests.module.css'

const ICONS: Record<PurchaseRequestAction, ReactNode> = {
  submit: <Send size={16} />,
  approve: <Check size={16} />,
  decline: <X size={16} />,
  request_changes: <Undo2 size={16} />,
  order: <ShoppingCart size={16} />,
  receive: <PackageCheck size={16} />,
  cancel: <CircleSlash size={16} />,
  reopen: <RotateCcw size={16} />,
}

const VARIANTS: Record<PurchaseRequestAction, 'primary' | 'secondary' | 'danger'> = {
  submit: 'primary',
  approve: 'primary',
  decline: 'danger',
  request_changes: 'secondary',
  order: 'primary',
  receive: 'primary',
  cancel: 'danger',
  reopen: 'secondary',
}

/** Actions that need no extra input. */
const DIRECT: readonly PurchaseRequestAction[] = ['submit', 'reopen']

export function serverErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError && error.isValidation ? error.errors : {}
}

export function generalMessage(error: unknown): string | null {
  return error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
}

export interface PurchaseRequestActionsProps {
  request: PurchaseRequestDetail
  canEdit: boolean
  onEdit: () => void
}

export function PurchaseRequestActions({ request, canEdit, onEdit }: PurchaseRequestActionsProps) {
  const toast = useToast()
  const perform = usePurchaseRequestAction(request.id)
  const [dialog, setDialog] = useState<PurchaseRequestAction | null>(null)
  const actions = useMemo(() => request.available_actions.filter(isPurchaseRequestAction), [request.available_actions])

  const runDirect = async (action: PurchaseRequestAction) => {
    try {
      await perform.mutateAsync({ action })
      toast.success(action === 'submit' ? `${request.display_number} submitted` : `${request.display_number} reopened as a draft`)
    } catch (error) {
      toast.error(`Could not ${PURCHASE_REQUEST_ACTION_LABELS[action].toLowerCase()}`, errorMessage(error))
    }
  }

  const close = () => {
    setDialog(null)
    perform.reset()
  }

  if (actions.length === 0 && !canEdit) return null

  return (
    <>
      <div className={styles.actionBar} role="group" aria-label="Purchase request actions">
        {canEdit && (
          <Button size="sm" onClick={onEdit}>
            Edit request
          </Button>
        )}
        {actions.map((action) => (
          <Button
            key={action}
            size="sm"
            variant={VARIANTS[action]}
            leadingIcon={ICONS[action]}
            loading={perform.isPending && DIRECT.includes(action)}
            onClick={() => (DIRECT.includes(action) ? void runDirect(action) : setDialog(action))}
          >
            {PURCHASE_REQUEST_ACTION_LABELS[action]}
          </Button>
        ))}
      </div>

      {dialog === 'approve' && <ApproveDialog request={request} onClose={close} />}
      {dialog === 'decline' && <CommentDialog request={request} action="decline" onClose={close} />}
      {dialog === 'request_changes' && <CommentDialog request={request} action="request_changes" onClose={close} />}
      {dialog === 'order' && <OrderDialog request={request} onClose={close} />}
      {dialog === 'receive' && <ReceiveDialog request={request} onClose={close} />}
      {dialog === 'cancel' && <CancelDialog request={request} onClose={close} />}
    </>
  )
}

interface DialogProps {
  request: PurchaseRequestDetail
  onClose: () => void
}

/* Approve ---------------------------------------------------------------------- */

function ApproveDialog({ request, onClose }: DialogProps) {
  const toast = useToast()
  const perform = usePurchaseRequestAction(request.id)
  const form = useForm<ApproveValues>({ resolver: zodResolver(ApproveInput), defaultValues: { comment: '', approved_total: '' } })
  const fieldErrors = serverErrors(perform.error)
  const general = generalMessage(perform.error)

  const submit = form.handleSubmit(async (values) => {
    try {
      const updated = await perform.mutateAsync({ action: 'approve', body: toApprovePayload(values) })
      toast.success(`${updated.display_number} approved`, `It is now ${updated.status.replace(/_/g, ' ')}.`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not approve this request', errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={`Approve ${request.display_number}?`}
      description={`Estimated total ${formatMoney(request.estimated_total ?? 0)}. Approving moves it to the next step.`}
      preventClose={perform.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={perform.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="pr-approve-form" loading={perform.isPending}>
            Approve
          </Button>
        </>
      }
    >
      <form id="pr-approve-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {general && <InlineAlert tone="danger">{general}</InlineAlert>}
        <FormField
          label="Approved total"
          optionalLabel
          hint="Leave blank to approve the estimated total."
          error={form.formState.errors.approved_total?.message ?? fieldErrors.approved_total}
        >
          <Input {...form.register('approved_total')} inputMode="decimal" placeholder={String(request.estimated_total ?? 0)} data-autofocus />
        </FormField>
        <FormField label="Comment" optionalLabel error={form.formState.errors.comment?.message ?? fieldErrors.comment}>
          <Textarea {...form.register('comment')} rows={3} placeholder="Anything the requester should know." />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Decline and request changes ---------------------------------------------------- */

function CommentDialog({ request, action, onClose }: DialogProps & { action: 'decline' | 'request_changes' }) {
  const toast = useToast()
  const perform = usePurchaseRequestAction(request.id)
  const form = useForm<CommentValues>({ resolver: zodResolver(CommentActionInput), defaultValues: { comment: '' } })
  const fieldErrors = serverErrors(perform.error)
  const general = generalMessage(perform.error)
  const declining = action === 'decline'

  const submit = form.handleSubmit(async (values) => {
    try {
      await perform.mutateAsync({ action, body: { comment: values.comment.trim() } })
      toast.success(declining ? `${request.display_number} declined` : `Changes requested on ${request.display_number}`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error(declining ? 'Could not decline this request' : 'Could not request changes', errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={declining ? `Decline ${request.display_number}?` : `Request changes on ${request.display_number}?`}
      description={declining ? 'The request closes as declined and the requester is notified with your reason.' : 'The request goes back to draft so the requester can edit and resubmit it.'}
      preventClose={perform.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={perform.isPending}>
            Cancel
          </Button>
          <Button variant={declining ? 'danger' : 'primary'} type="submit" form="pr-comment-form" loading={perform.isPending}>
            {declining ? 'Decline' : 'Request changes'}
          </Button>
        </>
      }
    >
      <form id="pr-comment-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {general && <InlineAlert tone="danger">{general}</InlineAlert>}
        <FormField label={declining ? 'Reason' : 'What needs to change?'} required error={form.formState.errors.comment?.message ?? fieldErrors.comment}>
          <Textarea {...form.register('comment')} rows={4} data-autofocus placeholder={declining ? 'Why is this being declined?' : 'Tell the requester what to adjust.'} />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Cancel ------------------------------------------------------------------------- */

function CancelDialog({ request, onClose }: DialogProps) {
  const toast = useToast()
  const perform = usePurchaseRequestAction(request.id)
  const form = useForm<CancelValues>({ resolver: zodResolver(CancelInput), defaultValues: { comment: '' } })
  const fieldErrors = serverErrors(perform.error)
  const general = generalMessage(perform.error)

  const submit = form.handleSubmit(async (values) => {
    const comment = (values.comment ?? '').trim()
    try {
      await perform.mutateAsync({ action: 'cancel', body: comment ? { comment } : {} })
      toast.success(`${request.display_number} canceled`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not cancel this request', errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={`Cancel ${request.display_number}?`}
      description="The request closes as canceled. A reviewer can reopen it as a draft later."
      preventClose={perform.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={perform.isPending}>
            Keep it
          </Button>
          <Button variant="danger" type="submit" form="pr-cancel-form" loading={perform.isPending}>
            Cancel request
          </Button>
        </>
      }
    >
      <form id="pr-cancel-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {general && <InlineAlert tone="danger">{general}</InlineAlert>}
        <FormField label="Comment" optionalLabel error={form.formState.errors.comment?.message ?? fieldErrors.comment}>
          <Textarea {...form.register('comment')} rows={3} data-autofocus placeholder="Why is this being canceled?" />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Order ------------------------------------------------------------------------- */

function OrderDialog({ request, onClose }: DialogProps) {
  const toast = useToast()
  const perform = usePurchaseRequestAction(request.id)
  const form = useForm<OrderValues>({
    resolver: zodResolver(OrderInput),
    defaultValues: { order_reference: '', ordered_at: '', approved_total: '', comment: '' },
  })
  const fieldErrors = serverErrors(perform.error)
  const general = generalMessage(perform.error)

  const submit = form.handleSubmit(async (values) => {
    try {
      await perform.mutateAsync({ action: 'order', body: toOrderPayload(values, fromDateTimeLocal((values.ordered_at ?? '').trim())) })
      toast.success(`${request.display_number} marked as ordered`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not mark this request as ordered', errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Mark ${request.display_number} as ordered`}
      description="Record the order so the parts show as on order until they arrive."
      preventClose={perform.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={perform.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="pr-order-form" loading={perform.isPending}>
            Mark as ordered
          </Button>
        </>
      }
    >
      <form id="pr-order-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {general && <InlineAlert tone="danger">{general}</InlineAlert>}
        <FormField label="Order reference" optionalLabel hint="Purchase order or confirmation number." error={form.formState.errors.order_reference?.message ?? fieldErrors.order_reference}>
          <Input {...form.register('order_reference')} data-autofocus maxLength={120} placeholder="e.g. PO-2291" />
        </FormField>
        <FormField label="Ordered at" optionalLabel hint="Leave blank to use now." error={form.formState.errors.ordered_at?.message ?? fieldErrors.ordered_at}>
          <DateTimeInput {...form.register('ordered_at')} />
        </FormField>
        <FormField label="Approved total" optionalLabel hint={`Estimated ${formatMoney(request.estimated_total ?? 0)}.`} error={form.formState.errors.approved_total?.message ?? fieldErrors.approved_total}>
          <Input {...form.register('approved_total')} inputMode="decimal" />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Receive ------------------------------------------------------------------------ */

function ReceiveDialog({ request, onClose }: DialogProps) {
  const toast = useToast()
  const perform = usePurchaseRequestAction(request.id)
  const locations = useLocations({ limit: 200 })
  const open = useMemo(() => request.items.filter((item) => outstandingQuantity(item) > 0), [request.items])
  const schema = useMemo(() => receiveSchema(request.items), [request.items])

  const form = useForm<ReceiveValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      note: '',
      lines: open.map((item) => ({ item_id: item.id, quantity: String(outstandingQuantity(item)), location_id: item.receive_location?.id ?? null })),
    },
  })
  const { fields } = useFieldArray({ control: form.control, name: 'lines' })
  const fieldErrors = serverErrors(perform.error)
  const general = generalMessage(perform.error)
  const locationOptions = (locations.data?.items ?? []).map((location) => ({ value: location.id, label: location.path.join(' › ') }))

  const submit = form.handleSubmit(async (values) => {
    try {
      const updated = await perform.mutateAsync({ action: 'receive', body: toReceivePayload(values) })
      toast.success(`Receipt recorded on ${updated.display_number}`, updated.status === 'received' ? 'Everything has arrived.' : 'Some lines are still outstanding.')
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not record the receipt', errorMessage(error))
    }
  })

  const linesError = form.formState.errors.lines?.root?.message ?? form.formState.errors.lines?.message ?? fieldErrors.lines

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Receive items on ${request.display_number}`}
      description="Enter what arrived. Stocked lines post a receipt into inventory at the location you choose."
      preventClose={perform.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={perform.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="pr-receive-form" loading={perform.isPending} disabled={open.length === 0}>
            Record receipt
          </Button>
        </>
      }
    >
      <form id="pr-receive-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {general && <InlineAlert tone="danger">{general}</InlineAlert>}
        {linesError && <InlineAlert tone="danger">{linesError}</InlineAlert>}
        {open.length === 0 ? (
          <p className={styles.muted}>Every line on this request has already been received.</p>
        ) : (
          fields.map((field, index) => {
            const item = open[index]
            const remaining = outstandingQuantity(item)
            const quantityError = form.formState.errors.lines?.[index]?.quantity?.message ?? fieldErrors[`lines[${index}].quantity`]
            const locationError = form.formState.errors.lines?.[index]?.location_id?.message ?? fieldErrors[`lines[${index}].location_id`]
            return (
              <div key={field.id} className={styles.receiveRow}>
                <div className={styles.receiveHead}>
                  <strong>{item.description}</strong>
                  <span className={styles.muted}>
                    {remaining} {item.part?.unit ?? ''} outstanding
                  </span>
                </div>
                <div className={styles.receiveFields}>
                  <FormField label={`Quantity received for ${item.description}`} error={quantityError}>
                    <Input {...form.register(`lines.${index}.quantity` as const)} inputMode="decimal" data-autofocus={index === 0 ? true : undefined} />
                  </FormField>
                  <FormField label={`Location for ${item.description}`} optionalLabel hint={item.part ? undefined : 'Free-text lines do not move stock.'} error={locationError}>
                    <Combobox
                      options={locationOptions}
                      loading={locations.isPending}
                      value={form.watch(`lines.${index}.location_id`) ?? null}
                      onChange={(value) => form.setValue(`lines.${index}.location_id` as const, value, { shouldDirty: true })}
                      placeholder="Default location"
                      aria-label={`Location for ${item.description}`}
                      disabled={!item.part}
                    />
                  </FormField>
                </div>
              </div>
            )
          })
        )}
        <FormField label="Note" optionalLabel error={form.formState.errors.note?.message ?? fieldErrors.note}>
          <Textarea {...form.register('note')} rows={2} placeholder="Packing slip number, condition on arrival." />
        </FormField>
        <p className={styles.muted}>Approved total {money(request.approved_total ?? request.estimated_total)}.</p>
      </form>
    </Dialog>
  )
}

export { toFormPath }
