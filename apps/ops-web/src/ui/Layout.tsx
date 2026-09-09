import { ArrowLeft, Check, ChevronDown, Search, X } from 'lucide-react'
import { forwardRef, useEffect, useId, useMemo, useRef, useState, type InputHTMLAttributes, type KeyboardEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { Button } from './Button'
import { DropdownMenu, type MenuItem } from './DropdownMenu'
import { Popover, useAnchor } from './Popover'
import styles from './layout.module.css'

/* Page header ---------------------------------------------------------------- */

export interface PageHeaderProps {
  title: ReactNode
  subtitle?: ReactNode
  viewSelector?: ReactNode
  actions?: ReactNode
  /** Filter chip row rendered under the title row. */
  filters?: ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, viewSelector, actions, filters, className }: PageHeaderProps) {
  return (
    <header className={cn(styles.header, className)}>
      <div className={styles.headerRow}>
        <div className={styles.headerTitleGroup}>
          <div style={{ minWidth: 0 }}>
            <h1 className={styles.headerTitle}>{title}</h1>
            {subtitle && <p className={styles.headerSubtitle}>{subtitle}</p>}
          </div>
          {viewSelector}
        </div>
        {actions && <div className={styles.headerActions}>{actions}</div>}
      </div>
      {filters && (
        <div className={styles.filterRow} role="group" aria-label="Filters">
          {filters}
        </div>
      )}
    </header>
  )
}

/* Search field --------------------------------------------------------------- */

export interface SearchFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value' | 'size'> {
  value: string
  onChange: (value: string) => void
  onDebouncedChange?: (value: string) => void
  debounceMs?: number
  compact?: boolean
  block?: boolean
  shortcutHint?: string
  label?: string
}

export const SearchField = forwardRef<HTMLInputElement, SearchFieldProps>(function SearchField(
  { value, onChange, onDebouncedChange, debounceMs = 250, compact, block, shortcutHint, label = 'Search', className, placeholder = 'Search', ...rest },
  ref,
) {
  const timer = useRef<number>(0)
  useEffect(() => {
    if (!onDebouncedChange) return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => onDebouncedChange(value), debounceMs)
    return () => window.clearTimeout(timer.current)
  }, [value, debounceMs, onDebouncedChange])
  return (
    <div className={cn(styles.search, block && styles.search_block, className)} role="search">
      <Search className={styles.searchIcon} size={16} aria-hidden="true" />
      <input
        ref={ref}
        type="search"
        aria-label={label}
        placeholder={placeholder}
        className={cn(styles.searchInput, compact && styles.searchInput_compact)}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && value) {
            event.stopPropagation()
            onChange('')
          }
        }}
        {...rest}
      />
      {value ? (
        <button type="button" className={styles.searchClear} aria-label="Clear search" onClick={() => onChange('')}>
          <X size={14} aria-hidden="true" />
        </button>
      ) : shortcutHint ? (
        <kbd className={styles.searchKbd} aria-hidden="true">
          {shortcutHint}
        </kbd>
      ) : null}
    </div>
  )
})

/* Tabs ----------------------------------------------------------------------- */

export interface TabItem<T extends string> {
  value: T
  label: ReactNode
  count?: number | null
  disabled?: boolean
}

export function Tabs<T extends string>({ value, onChange, items, label, className }: { value: T; onChange: (value: T) => void; items: TabItem<T>[]; label: string; className?: string }) {
  const refs = useRef<Array<HTMLButtonElement | null>>([])
  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const enabled = items.map((item, i) => (item.disabled ? -1 : i)).filter((i) => i >= 0)
    const position = enabled.indexOf(index)
    let next = position
    if (event.key === 'ArrowRight') next = (position + 1) % enabled.length
    else if (event.key === 'ArrowLeft') next = (position - 1 + enabled.length) % enabled.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = enabled.length - 1
    else return
    event.preventDefault()
    const target = enabled[next]
    refs.current[target]?.focus()
    onChange(items[target].value)
  }
  return (
    <div role="tablist" aria-label={label} className={cn(styles.tabs, className)}>
      {items.map((item, index) => {
        const selected = item.value === value
        return (
          <button
            key={item.value}
            ref={(node) => {
              refs.current[index] = node
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            className={styles.tab}
            onClick={() => onChange(item.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {item.label}
            {item.count !== undefined && item.count !== null && <span className={styles.tabCount}>{item.count}</span>}
          </button>
        )
      })}
    </div>
  )
}

/* Segmented control ---------------------------------------------------------- */

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T
  onChange: (value: T) => void
  options: Array<{ value: T; label: ReactNode; icon?: ReactNode; tone?: 'danger' }>
  label: string
  className?: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn(styles.segmented, className)}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          className={cn(styles.segment, option.tone === 'danger' && styles.segment_danger)}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => {
            const index = options.findIndex((o) => o.value === value)
            if (event.key === 'ArrowRight') onChange(options[(index + 1) % options.length].value)
            if (event.key === 'ArrowLeft') onChange(options[(index - 1 + options.length) % options.length].value)
          }}
        >
          {option.icon}
          {option.label}
        </button>
      ))}
    </div>
  )
}

/* Filter chip ---------------------------------------------------------------- */

export interface FilterOption {
  value: string
  label: string
  count?: number
  color?: string
  description?: string
}

export interface FilterChipProps {
  label: string
  options: FilterOption[]
  value: string[]
  onChange: (value: string[]) => void
  multiple?: boolean
  searchable?: boolean
  loading?: boolean
  emptyText?: string
  /** Called when the popover opens; use to lazily load options. */
  onOpen?: () => void
}

export function FilterChip({ label, options, value, onChange, multiple = true, searchable, loading, emptyText = 'No options', onOpen }: FilterChipProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const { anchor, ref } = useAnchor<HTMLButtonElement>()
  const id = useId()
  const active = value.length > 0
  const selectedLabels = options.filter((o) => value.includes(o.value)).map((o) => o.label)
  const summary = !active ? '' : selectedLabels.length === 1 ? selectedLabels[0] : selectedLabels.length === 0 ? `${value.length} selected` : `${selectedLabels[0]} +${selectedLabels.length - 1}`
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
  }, [options, query])

  const toggle = (option: FilterOption) => {
    if (multiple) {
      onChange(value.includes(option.value) ? value.filter((v) => v !== option.value) : [...value, option.value])
    } else {
      onChange(value[0] === option.value ? [] : [option.value])
      setOpen(false)
    }
  }

  return (
    <>
      <button
        ref={ref}
        type="button"
        className={cn(styles.chip, active && styles.chip_active)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => {
          if (!open) onOpen?.()
          setOpen(!open)
        }}
      >
        <span>{label}</span>
        {active && (
          <>
            <span aria-hidden="true">:</span>
            <span className={styles.chipValue}>{summary}</span>
          </>
        )}
        {active ? (
          <span
            role="button"
            tabIndex={0}
            aria-label={`Clear ${label} filter`}
            className={styles.chipClear}
            onClick={(event) => {
              event.stopPropagation()
              onChange([])
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                event.stopPropagation()
                onChange([])
              }
            }}
          >
            <X size={12} aria-hidden="true" />
          </span>
        ) : (
          <ChevronDown size={14} aria-hidden="true" />
        )}
      </button>
      <Popover open={open} onOpenChange={setOpen} anchor={anchor} id={id} role="dialog" labelledBy={undefined} className={styles.filterPanel}>
        <span className="sr-only">{label} filter</span>
        {searchable && (
          <div className={styles.filterSearch}>
            <SearchField value={query} onChange={setQuery} compact block placeholder={`Search ${label.toLowerCase()}`} data-autofocus />
          </div>
        )}
        <div className={styles.filterList} role={multiple ? 'group' : 'radiogroup'} aria-label={label}>
          {loading ? (
            <div className={styles.filterEmpty}>Loading…</div>
          ) : visible.length === 0 ? (
            <div className={styles.filterEmpty}>{emptyText}</div>
          ) : (
            visible.map((option) => {
              const checked = value.includes(option.value)
              return (
                <button
                  key={option.value}
                  type="button"
                  role={multiple ? 'checkbox' : 'radio'}
                  aria-checked={checked}
                  className={styles.filterOption}
                  onClick={() => toggle(option)}
                >
                  <span className={cn(styles.filterOptionBox, !multiple && styles.filterOptionBox_radio)} aria-hidden="true">
                    {checked && <Check size={12} strokeWidth={3} />}
                  </span>
                  {option.color && <span style={{ width: 8, height: 8, borderRadius: 4, background: option.color, flex: 'none' }} aria-hidden="true" />}
                  <span className={styles.filterOptionLabel}>{option.label}</span>
                  {option.count !== undefined && <span className={styles.filterOptionCount}>{option.count}</span>}
                </button>
              )
            })
          )}
        </div>
        <div className={styles.filterFooter}>
          <span style={{ color: 'var(--color-text-muted)' }}>{value.length ? `${value.length} selected` : 'None selected'}</span>
          <Button variant="link" size="sm" onClick={() => onChange([])} disabled={!active}>
            Clear
          </Button>
        </div>
      </Popover>
    </>
  )
}

/* View selector (saved views / list modes) ------------------------------------ */

export function ViewSelector<T extends string>({ value, options, onChange, label = 'View' }: { value: T; options: Array<{ value: T; label: string; description?: string }>; onChange: (value: T) => void; label?: string }) {
  const current = options.find((o) => o.value === value)
  const items: MenuItem[] = options.map((option) => ({
    key: option.value,
    label: option.label,
    description: option.description,
    checked: option.value === value,
    onSelect: () => onChange(option.value),
  }))
  return (
    <DropdownMenu
      items={items}
      label={label}
      trigger={(props) => (
        <button type="button" {...props} ref={props.ref} className={styles.viewSelector} aria-label={`${label}: ${current?.label ?? ''}`}>
          <span>{current?.label}</span>
          <ChevronDown size={16} aria-hidden="true" />
        </button>
      )}
    />
  )
}

/* Master / detail ------------------------------------------------------------ */

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(styles.page, className)}>{children}</div>
}

export interface MasterDetailLayoutProps {
  list: ReactNode
  detail: ReactNode
  /** On narrow screens, whether the detail pane is the visible one. */
  detailOpen: boolean
  backTo?: string
  backLabel?: string
  listToolbar?: ReactNode
  className?: string
}

export function MasterDetailLayout({ list, detail, detailOpen, backTo, backLabel = 'Back to list', listToolbar, className }: MasterDetailLayoutProps) {
  return (
    <div className={cn(styles.split, detailOpen && styles.split_showDetail, className)}>
      <section className={styles.splitList} aria-label="List">
        {listToolbar && <div className={styles.splitToolbar}>{listToolbar}</div>}
        <div className={cn(styles.splitScroll, 'scroll-y')}>{list}</div>
      </section>
      <section className={styles.splitDetail} aria-label="Details">
        {backTo && (
          <div className={styles.backBar}>
            <Link to={backTo} className={styles.viewSelector}>
              <ArrowLeft size={16} aria-hidden="true" />
              {backLabel}
            </Link>
          </div>
        )}
        {detail}
      </section>
    </div>
  )
}

export function ListToolbarSpacer() {
  return <span className={styles.splitToolbarSpacer} />
}

/* List row ------------------------------------------------------------------- */

export interface ListRowProps {
  to?: string
  onClick?: () => void
  selected?: boolean
  leading?: ReactNode
  title: ReactNode
  meta?: ReactNode
  trailing?: ReactNode
  compact?: boolean
  className?: string
  'data-testid'?: string
}

export function ListRow({ to, onClick, selected, leading, title, meta, trailing, compact, className, ...rest }: ListRowProps) {
  const content = (
    <>
      {leading && <span className={styles.rowLeading}>{leading}</span>}
      <span className={styles.rowBody}>
        <span className={styles.rowTitle}>{title}</span>
        {meta && <span className={styles.rowMeta}>{meta}</span>}
      </span>
      {trailing && <span className={styles.rowTrailing}>{trailing}</span>}
    </>
  )
  const cls = cn(styles.row, compact && styles.row_compact, selected && styles.row_selected, className)
  if (to) {
    return (
      <Link to={to} className={cls} aria-current={selected ? 'true' : undefined} data-testid={rest['data-testid']}>
        {content}
      </Link>
    )
  }
  return (
    <div role="button" tabIndex={0} className={cls} aria-current={selected ? 'true' : undefined} onClick={onClick} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onClick?.()} data-testid={rest['data-testid']}>
      {content}
    </div>
  )
}

/* Detail panel --------------------------------------------------------------- */

export interface DetailPanelProps {
  eyebrow?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
  className?: string
}

export function DetailPanel({ eyebrow, title, subtitle, actions, children, footer, className }: DetailPanelProps) {
  return (
    <article className={cn(styles.detail, className)}>
      <header className={styles.detailHeader}>
        <div className={styles.detailHeaderMain}>
          {eyebrow && <div className={styles.detailEyebrow}>{eyebrow}</div>}
          <h2 className={styles.detailTitle}>{title}</h2>
          {subtitle && <p className={styles.detailSubtitle}>{subtitle}</p>}
        </div>
        {actions && <div className={styles.detailActions}>{actions}</div>}
      </header>
      <div className={cn(styles.detailBody, 'scroll-y')}>{children}</div>
      {footer && <footer className={styles.detailFooter}>{footer}</footer>}
    </article>
  )
}

export function Card({ title, actions, children, flush, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean; className?: string }) {
  return (
    <section className={cn(styles.card, className)}>
      {(title || actions) && (
        <header className={styles.cardHeader}>
          <h3 className={styles.cardTitle}>{title}</h3>
          {actions}
        </header>
      )}
      <div className={cn(styles.cardBody, flush && styles.cardBody_flush)}>{children}</div>
    </section>
  )
}

export function Stack({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(styles.stack, className)}>{children}</div>
}

export function Grid2({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn(styles.grid2, className)}>{children}</div>
}

export function FieldList({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return (
    <dl className={styles.fieldList}>
      {items.map((item) => (
        <div key={item.label} style={{ display: 'contents' }}>
          <dt>{item.label}</dt>
          <dd>{item.value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
