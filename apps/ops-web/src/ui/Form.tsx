import { AlertCircle, Check, ChevronDown, X } from 'lucide-react'
import {
  createContext,
  forwardRef,
  useContext,
  useId,
  useMemo,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { cn } from '@/lib/cn'
import { Popover, useAnchor } from './Popover'
import styles from './form.module.css'

/* FormField ------------------------------------------------------------------ */

interface FieldContextValue {
  id: string
  describedBy?: string
  invalid: boolean
}

const FieldContext = createContext<FieldContextValue | null>(null)

export interface FormFieldProps {
  label: ReactNode
  children: ReactNode
  hint?: ReactNode
  error?: string | null
  required?: boolean
  optionalLabel?: boolean
  className?: string
  /** Render the label as a plain span (for composite controls with their own labelling). */
  asGroup?: boolean
}

export function FormField({ label, children, hint, error, required, optionalLabel, className, asGroup }: FormFieldProps) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined
  const value = useMemo(() => ({ id, describedBy, invalid: Boolean(error) }), [id, describedBy, error])
  const LabelTag = asGroup ? 'span' : 'label'
  return (
    <FieldContext.Provider value={value}>
      <div className={cn(styles.field, className)} role={asGroup ? 'group' : undefined} aria-labelledby={asGroup ? `${id}-label` : undefined}>
        <LabelTag id={`${id}-label`} htmlFor={asGroup ? undefined : id} className={styles.label}>
          <span>{label}</span>
          {required && (
            <span className={styles.required} aria-hidden="true">
              *
            </span>
          )}
          {optionalLabel && !required && <span className={styles.optional}>Optional</span>}
        </LabelTag>
        {children}
        {hint && !error && (
          <p id={hintId} className={styles.hint}>
            {hint}
          </p>
        )}
        {error && (
          <p id={errorId} className={styles.error} role="alert">
            <AlertCircle size={13} aria-hidden="true" />
            {error}
          </p>
        )}
      </div>
    </FieldContext.Provider>
  )
}

export function FieldRow({ children }: { children: ReactNode }) {
  return <div className={styles.fieldRow}>{children}</div>
}

export function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={styles.formSection}>
      <h3 className={styles.formSectionTitle}>{title}</h3>
      <div style={{ display: 'grid', gap: 'var(--space-4)' }}>{children}</div>
    </div>
  )
}

function useFieldProps() {
  const field = useContext(FieldContext)
  return {
    id: field?.id,
    'aria-describedby': field?.describedBy,
    'aria-invalid': field?.invalid ? ('true' as const) : undefined,
  }
}

/* Input ---------------------------------------------------------------------- */

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  compact?: boolean
  leadingIcon?: ReactNode
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input({ className, compact, leadingIcon, ...rest }, ref) {
  const field = useFieldProps()
  const input = <input ref={ref} className={cn(styles.control, compact && styles.control_compact, className)} {...field} {...rest} />
  if (!leadingIcon) return input
  return (
    <div className={styles.inputAffix}>
      <span className={styles.affixIcon} aria-hidden="true">
        {leadingIcon}
      </span>
      {input}
    </div>
  )
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  const field = useFieldProps()
  return <textarea ref={ref} className={cn(styles.control, styles.textarea, className)} {...field} {...rest} />
})

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  compact?: boolean
  placeholder?: string
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ className, compact, placeholder, children, ...rest }, ref) {
  const field = useFieldProps()
  return (
    <div className={styles.selectWrap}>
      <select ref={ref} className={cn(styles.control, styles.select, compact && styles.control_compact, className)} {...field} {...rest}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {children}
      </select>
      <ChevronDown className={styles.selectChevron} size={16} aria-hidden="true" />
    </div>
  )
})

export function Checkbox({ label, hint, checked, onChange, disabled, name }: { label: ReactNode; hint?: ReactNode; checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean; name?: string }) {
  return (
    <label className={styles.check}>
      <input type="checkbox" name={name} checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span className={styles.checkBox} aria-hidden="true">
        {checked && <Check size={12} strokeWidth={3} />}
      </span>
      <span className={styles.checkLabel}>
        {label}
        {hint && <span className={styles.checkHint}>{hint}</span>}
      </span>
    </label>
  )
}

/* Date pickers: native inputs are the most accessible and keyboard friendly. */

export const DateInput = forwardRef<HTMLInputElement, Omit<InputProps, 'type'>>(function DateInput(props, ref) {
  return <Input ref={ref} type="date" {...props} />
})

export const DateTimeInput = forwardRef<HTMLInputElement, Omit<InputProps, 'type'>>(function DateTimeInput(props, ref) {
  return <Input ref={ref} type="datetime-local" {...props} />
})

/* Avatar --------------------------------------------------------------------- */

export function Avatar({ name, src, size }: { name: string; src?: string | null; size?: 'lg' }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
  return (
    <span className={cn(styles.avatar, size === 'lg' && styles.avatar_lg)} title={name} aria-label={name} role="img">
      {src ? <img src={src} alt="" /> : initials || '?'}
    </span>
  )
}

export function AvatarStack({ people, max = 3 }: { people: Array<{ id: number | string; name: string; avatar_url?: string | null }>; max?: number }) {
  const shown = people.slice(0, max)
  const rest = people.length - shown.length
  return (
    <span className={styles.avatarStack} aria-label={people.map((p) => p.name).join(', ')}>
      {shown.map((person) => (
        <Avatar key={person.id} name={person.name} src={person.avatar_url} />
      ))}
      {rest > 0 && <span className={styles.avatar}>+{rest}</span>}
    </span>
  )
}

/* Combobox ------------------------------------------------------------------- */

export interface ComboOption<V extends string | number = string> {
  value: V
  label: string
  meta?: string
  icon?: ReactNode
  disabled?: boolean
}

interface ComboboxBaseProps<V extends string | number> {
  options: ComboOption<V>[]
  placeholder?: string
  disabled?: boolean
  loading?: boolean
  /** Server-side search hook: called with the typed text (debounced by the caller). */
  onSearch?: (query: string) => void
  emptyText?: string
  compact?: boolean
  clearable?: boolean
  renderOption?: (option: ComboOption<V>) => ReactNode
  'aria-label'?: string
}

export type ComboboxProps<V extends string | number> =
  | (ComboboxBaseProps<V> & { multiple?: false; value: V | null; onChange: (value: V | null) => void })
  | (ComboboxBaseProps<V> & { multiple: true; value: V[]; onChange: (value: V[]) => void })

export function Combobox<V extends string | number = string>(props: ComboboxProps<V>) {
  const { options, placeholder = 'Select…', disabled, loading, onSearch, emptyText = 'No matches', compact, clearable = true, renderOption } = props
  const field = useFieldProps()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const { anchor, ref } = useAnchor<HTMLDivElement>()
  const listId = useId()
  const selectedValues = useMemo<V[]>(() => (props.multiple ? props.value : props.value === null ? [] : [props.value]), [props.multiple, props.value])
  const selectedOptions = selectedValues.map((v) => options.find((o) => o.value === v)).filter(Boolean) as ComboOption<V>[]

  const visible = useMemo(() => {
    if (onSearch) return options
    const q = query.trim().toLowerCase()
    return q ? options.filter((o) => o.label.toLowerCase().includes(q) || o.meta?.toLowerCase().includes(q)) : options
  }, [options, query, onSearch])

  const listKey = `${visible.length}|${query}`
  const [lastListKey, setLastListKey] = useState(listKey)
  if (lastListKey !== listKey) {
    setLastListKey(listKey)
    setActive(0)
  }

  const select = (option: ComboOption<V>) => {
    if (option.disabled) return
    if (props.multiple) {
      const next = props.value.includes(option.value) ? props.value.filter((v) => v !== option.value) : [...props.value, option.value]
      props.onChange(next)
      setQuery('')
      inputRef.current?.focus()
    } else {
      props.onChange(option.value)
      setQuery('')
      setOpen(false)
    }
  }

  const remove = (value: V) => {
    if (props.multiple) props.onChange(props.value.filter((v) => v !== value))
    else props.onChange(null)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!open) setOpen(true)
      else setActive((a) => Math.min(a + 1, visible.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (event.key === 'Enter') {
      if (open && visible[active]) {
        event.preventDefault()
        select(visible[active])
      }
    } else if (event.key === 'Backspace' && !query && selectedValues.length) {
      remove(selectedValues[selectedValues.length - 1])
    } else if (event.key === 'Escape' && open) {
      event.stopPropagation()
      setOpen(false)
    }
  }

  const showInput = props.multiple || open || selectedOptions.length === 0

  return (
    <>
      <div
        ref={ref}
        role="presentation"
        className={cn(styles.control, styles.comboControl, compact && styles.control_compact)}
        data-disabled={disabled || undefined}
        data-invalid={field['aria-invalid']}
        onClick={() => {
          if (disabled) return
          setOpen(true)
          inputRef.current?.focus()
        }}
      >
        {props.multiple &&
          selectedOptions.map((option) => (
            <span key={String(option.value)} className={styles.comboToken}>
              {option.label}
              <button
                type="button"
                className={styles.comboTokenRemove}
                aria-label={`Remove ${option.label}`}
                onClick={(event) => {
                  event.stopPropagation()
                  remove(option.value)
                }}
              >
                <X size={12} aria-hidden="true" />
              </button>
            </span>
          ))}
        {!props.multiple && !showInput && (
          <span style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
            {selectedOptions[0]?.icon}
            {selectedOptions[0]?.label}
          </span>
        )}
        {showInput && (
          <input
            ref={inputRef}
            id={field.id}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={open && visible[active] ? `${listId}-${String(visible[active].value)}` : undefined}
            aria-describedby={field['aria-describedby']}
            aria-invalid={field['aria-invalid']}
            aria-label={props['aria-label']}
            className={styles.comboInput}
            placeholder={selectedOptions.length ? '' : placeholder}
            value={query}
            disabled={disabled}
            onChange={(event) => {
              setQuery(event.target.value)
              onSearch?.(event.target.value)
              if (!open) setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            autoComplete="off"
          />
        )}
        {!props.multiple && clearable && selectedOptions.length > 0 && !disabled && (
          <button
            type="button"
            className={styles.comboTokenRemove}
            aria-label="Clear selection"
            onClick={(event) => {
              event.stopPropagation()
              props.onChange(null)
            }}
          >
            <X size={14} aria-hidden="true" />
          </button>
        )}
        <ChevronDown size={16} className={styles.comboChevron} aria-hidden="true" />
      </div>
      <Popover open={open && !disabled} onOpenChange={setOpen} anchor={anchor} matchWidth role="presentation" focusOnOpen={false} returnFocus={false} className={styles.comboList}>
        <ul id={listId} role="listbox" aria-multiselectable={props.multiple || undefined}>
          {loading ? (
            <li className={styles.comboEmpty}>Loading…</li>
          ) : visible.length === 0 ? (
            <li className={styles.comboEmpty}>{emptyText}</li>
          ) : (
            visible.map((option, index) => {
              const selected = selectedValues.includes(option.value)
              return (
                <li
                  key={String(option.value)}
                  id={`${listId}-${String(option.value)}`}
                  role="option"
                  aria-selected={selected}
                  aria-disabled={option.disabled || undefined}
                  data-active={index === active ? 'true' : undefined}
                  className={styles.comboOption}
                  onMouseEnter={() => setActive(index)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => select(option)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      select(option)
                    }
                  }}
                >
                  {renderOption ? (
                    renderOption(option)
                  ) : (
                    <>
                      {option.icon}
                      <span>{option.label}</span>
                      {option.meta && <span className={styles.comboOptionMeta}>{option.meta}</span>}
                      {selected && <Check size={14} aria-hidden="true" style={{ color: 'var(--color-primary)' }} />}
                    </>
                  )}
                </li>
              )
            })
          )}
        </ul>
      </Popover>
    </>
  )
}
