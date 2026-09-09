import { zodResolver } from '@hookform/resolvers/zod'
import { CalendarDays } from 'lucide-react'
import { useCallback, useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { CustomRangeInput, MAX_CUSTOM_DAYS, RANGE_KEYS, RANGE_LABELS, type RangeKey } from '@/api/contracts/reports'
import { Button, DateInput, FieldRow, FormField, Popover, SegmentedControl, useAnchor } from '@/ui'
import { daysAgoIso, formatRangeLabel, todayIso } from './format'
import styles from './reporting.module.css'

export interface RangeSelection {
  range: RangeKey
  start?: string
  end?: string
}

export interface RangeControlProps {
  value: RangeKey
  start?: string
  end?: string
  /** Whether the custom-range popover is open (owned by the page so alerts can open it). */
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Field messages returned by the API for `start` / `end`, mapped onto the form. */
  serverErrors?: Partial<Record<'start' | 'end', string>>
  onChange: (next: RangeSelection) => void
}

const OPTIONS = RANGE_KEYS.map((key) => ({ value: key, label: RANGE_LABELS[key] }))

/**
 * Preset segments plus a popover for a custom window. Choosing "Custom" only
 * opens the popover; the URL changes when the dates are applied, so the report
 * is never requested with a half-entered range.
 */
export function RangeControl({ value, start, end, open, onOpenChange, serverErrors, onChange }: RangeControlProps) {
  const { anchor, ref } = useAnchor<HTMLDivElement>()
  const form = useForm<CustomRangeInput>({
    resolver: zodResolver(CustomRangeInput),
    defaultValues: { start: start ?? daysAgoIso(29), end: end ?? todayIso() },
  })
  const { register, handleSubmit, reset, setError, formState } = form
  const isDirty = formState.isDirty
  const dirtyRef = useRef(false)
  useEffect(() => {
    dirtyRef.current = isDirty
  }, [isDirty])

  // Each time the popover opens, start from the range currently in the URL.
  useEffect(() => {
    if (open) reset({ start: start ?? daysAgoIso(29), end: end ?? todayIso() })
  }, [open, start, end, reset])

  useEffect(() => {
    if (!open || !serverErrors) return
    for (const field of ['start', 'end'] as const) {
      const message = serverErrors[field]
      if (message) setError(field, { type: 'server', message })
    }
  }, [open, serverErrors, setError])

  const requestClose = useCallback(() => {
    if (dirtyRef.current && !window.confirm('Discard the dates you entered?')) return
    onOpenChange(false)
  }, [onOpenChange])

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (next) onOpenChange(true)
      else requestClose()
    },
    [onOpenChange, requestClose],
  )

  const select = (key: RangeKey) => {
    if (key === 'custom') {
      onOpenChange(true)
      return
    }
    onOpenChange(false)
    onChange({ range: key })
  }

  const submit = handleSubmit((values) => {
    onChange({ range: 'custom', start: values.start, end: values.end })
    onOpenChange(false)
  })

  // While the popover is open the "Custom" segment reads as selected even before Apply.
  const shown: RangeKey = open ? 'custom' : value

  return (
    <div className={styles.rangeGroup} ref={ref}>
      <SegmentedControl<RangeKey> label="Date range" value={shown} onChange={select} options={OPTIONS} />
      {value === 'custom' && start && end && (
        <Button size="sm" leadingIcon={<CalendarDays size={14} />} onClick={() => onOpenChange(true)} aria-haspopup="dialog" aria-expanded={open}>
          {formatRangeLabel(start, end)}
        </Button>
      )}
      <Popover open={open} onOpenChange={handleOpenChange} anchor={anchor} placement="bottom-end" role="dialog" label="Custom date range" className={styles.rangePopover}>
        <form className={styles.rangeForm} noValidate onSubmit={submit}>
          <FieldRow>
            <FormField label="Start" required error={formState.errors.start?.message}>
              <DateInput {...register('start')} data-autofocus compact />
            </FormField>
            <FormField label="End" required error={formState.errors.end?.message}>
              <DateInput {...register('end')} compact />
            </FormField>
          </FieldRow>
          <p className={styles.rangeHint}>Up to {MAX_CUSTOM_DAYS} days, interpreted in the chapter&apos;s time zone.</p>
          <div className={styles.rangeFooter}>
            <Button variant="ghost" size="sm" onClick={requestClose}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" type="submit">
              Apply
            </Button>
          </div>
        </form>
      </Popover>
    </div>
  )
}
