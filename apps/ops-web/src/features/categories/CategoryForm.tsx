import { zodResolver } from '@hookform/resolvers/zod'
import { Check } from 'lucide-react'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { CATEGORY_COLOR_PRESETS, CategoryInput, DEFAULT_CATEGORY_COLOR, DEFAULT_CATEGORY_ICON, type Category, type CategoryPayload } from '@/api/contracts/categories'
import { Button, FormField, InlineAlert, Input, SearchField, SideSheet, Textarea } from '@/ui'
import { CATEGORY_ICONS, CategoryIconTile, iconLabel } from './icons'
import styles from './categories.module.css'

export interface CategoryFormProps {
  open: boolean
  mode: 'create' | 'edit'
  /** Existing category when editing. */
  initial?: Category | null
  submitting: boolean
  error: unknown
  onSubmit: (values: CategoryPayload) => Promise<void>
  onClose: () => void
}

const FIELDS: ReadonlyArray<keyof CategoryInput> = ['name', 'color', 'icon', 'description']

/**
 * Create/edit pane. The inner form mounts fresh every time the pane opens so
 * defaults come straight from `initial` and picker state starts clean.
 */
export function CategoryForm(props: CategoryFormProps) {
  if (!props.open) return null
  return <CategoryFormBody {...props} />
}

function CategoryFormBody({ mode, initial, submitting, error, onSubmit, onClose }: CategoryFormProps) {
  const editing = mode === 'edit'
  const form = useForm<CategoryInput>({
    resolver: zodResolver(CategoryInput),
    defaultValues: {
      name: editing ? (initial?.name ?? '') : '',
      color: editing ? (initial?.color ?? DEFAULT_CATEGORY_COLOR) : DEFAULT_CATEGORY_COLOR,
      icon: editing ? (initial?.icon ?? DEFAULT_CATEGORY_ICON) : DEFAULT_CATEGORY_ICON,
      description: editing ? (initial?.description ?? '') : '',
    },
  })
  const { register, control, handleSubmit, setError, setFocus, formState } = form
  const [iconQuery, setIconQuery] = useState('')
  const hexId = useId()

  const name = useWatch({ control, name: 'name' })
  const color = useWatch({ control, name: 'color' })
  const icon = useWatch({ control, name: 'icon' })

  // Start on the first field (the pane's own autofocus lands on its close button).
  useEffect(() => {
    setFocus('name')
  }, [setFocus])

  // The pane reads onRequestClose from its mount-time closure, so look up the live state.
  const dirty = formState.isDirty
  const closeState = useRef({ dirty, submitting })
  useEffect(() => {
    closeState.current = { dirty, submitting }
  }, [dirty, submitting])
  const confirmClose = useCallback(() => (closeState.current.dirty && !closeState.current.submitting ? window.confirm('Discard your changes?') : true), [])

  // Map server-side field errors onto the form; anything else shows as a general alert.
  useEffect(() => {
    if (error instanceof ApiError && error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) {
        if ((FIELDS as readonly string[]).includes(field)) setError(field as keyof CategoryInput, { type: 'server', message })
      }
    }
  }, [error, setError])

  const unmappedServerErrors = useMemo(() => {
    if (!(error instanceof ApiError && error.isValidation)) return []
    return Object.entries(error.errors)
      .filter(([field]) => !(FIELDS as readonly string[]).includes(field))
      .map(([field, message]) => `${field}: ${message}`)
  }, [error])
  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null

  const visibleIcons = useMemo(() => {
    const q = iconQuery.trim().toLowerCase()
    if (!q) return CATEGORY_ICONS
    return CATEGORY_ICONS.filter((option) => option.name.includes(q) || option.label.toLowerCase().includes(q) || option.keywords.includes(q))
  }, [iconQuery])
  const iconInPicker = CATEGORY_ICONS.some((option) => option.name === icon)

  return (
    <SideSheet
      open
      onClose={onClose}
      title={mode === 'create' ? 'New Category' : `Edit ${initial?.name ?? 'category'}`}
      subtitle={mode === 'create' ? 'Categories tag work orders so the chapter can see what kind of work is happening.' : undefined}
      onRequestClose={confirmClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="category-form" loading={submitting}>
            {mode === 'create' ? 'Create Category' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form
        id="category-form"
        noValidate
        className={styles.form}
        onSubmit={handleSubmit(async (values) => {
          await onSubmit({
            name: values.name,
            color: values.color,
            icon: values.icon,
            description: values.description ? values.description : null,
          })
        })}
      >
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {unmappedServerErrors.length > 0 && (
          <InlineAlert tone="danger" title="Please fix the following">
            <ul>
              {unmappedServerErrors.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </InlineAlert>
        )}

        <div className={styles.preview} data-testid="category-preview">
          <CategoryIconTile color={color} icon={icon} size="lg" />
          <div style={{ minWidth: 0 }}>
            <div className={styles.previewName}>{name || 'New category'}</div>
            <div className={styles.previewMeta}>
              {iconLabel(icon)} · <span className="mono">{color}</span>
            </div>
          </div>
        </div>

        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. Fabrication" maxLength={120} />
        </FormField>

        <Controller
          control={control}
          name="color"
          render={({ field }) => (
            <FormField label="Colour" required asGroup error={formState.errors.color?.message} hint="Pick a preset or enter any six-digit hex value.">
              <div role="radiogroup" aria-label="Colour presets" className={styles.swatches}>
                {CATEGORY_COLOR_PRESETS.map((preset) => {
                  const checked = field.value.trim().toLowerCase() === preset.hex
                  return (
                    <label key={preset.hex} className={styles.swatch} title={`${preset.name} ${preset.hex}`}>
                      <input type="radio" name="category-color" value={preset.hex} checked={checked} onChange={() => field.onChange(preset.hex)} className={styles.hiddenInput} />
                      <span className={styles.swatchFill} style={{ background: preset.hex }} aria-hidden="true">
                        {checked && <Check size={14} strokeWidth={3} />}
                      </span>
                      <span className="sr-only">{preset.name}</span>
                    </label>
                  )
                })}
              </div>
              <div className={styles.hexField}>
                <label htmlFor={hexId} className={styles.hexCaption}>
                  Hex value
                </label>
                <Input id={hexId} ref={field.ref} name={field.name} value={field.value} onChange={(event) => field.onChange(event.target.value)} onBlur={field.onBlur} placeholder="#0878d1" maxLength={7} className="mono" spellCheck={false} autoComplete="off" />
              </div>
            </FormField>
          )}
        />

        <Controller
          control={control}
          name="icon"
          render={({ field }) => (
            <FormField label="Icon" required asGroup error={formState.errors.icon?.message}>
              <SearchField compact block className={styles.iconSearch} value={iconQuery} onChange={setIconQuery} placeholder="Search icons" label="Search icons" />
              {!iconInPicker && field.value && (
                <p className={styles.iconNote}>
                  The current icon “{field.value}” is not in this picker. It stays until you choose another one.
                </p>
              )}
              <div role="radiogroup" aria-label="Icons" className={styles.iconGrid}>
                {visibleIcons.length === 0 ? (
                  <p className={styles.iconEmpty}>No icons match “{iconQuery.trim()}”.</p>
                ) : (
                  visibleIcons.map(({ name: iconName, label, Icon }) => (
                    <label key={iconName} className={styles.iconOption}>
                      <input type="radio" name="category-icon" value={iconName} checked={field.value === iconName} onChange={() => field.onChange(iconName)} className={styles.hiddenInput} />
                      <span className={styles.iconCard}>
                        <Icon size={18} aria-hidden="true" />
                        <span className={styles.iconOptionLabel}>{label}</span>
                      </span>
                    </label>
                  ))
                )}
              </div>
            </FormField>
          )}
        />

        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={3} placeholder="When to use this category, e.g. structural, drivetrain and mounting work." />
        </FormField>
      </form>
    </SideSheet>
  )
}
