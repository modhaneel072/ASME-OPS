import { ArrowRight, Bell, ClipboardList, Cpu, FolderKanban, MapPin, Package, Plus, Rocket, ShoppingCart, Tag, UserRound, type LucideIcon } from 'lucide-react'
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { labelFor } from '@/api/contracts/common'
import { groupSearchResults, SEARCH_DEFAULT_LIMIT, SEARCH_MIN_LENGTH, type SearchGroup, type SearchGroupKey, type SearchItem } from '@/api/contracts/search'
import { useSearch } from '@/api/queries/search'
import { useCan } from '@/lib/permissions'
import { Badge, Button, Dialog, SearchField } from '@/ui'
import styles from './search.module.css'

export interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

const GROUP_ICONS: Record<SearchGroupKey, LucideIcon> = {
  work_orders: ClipboardList,
  projects: FolderKanban,
  assets: Cpu,
  parts: Package,
  purchase_requests: ShoppingCart,
  locations: MapPin,
  categories: Tag,
  users: UserRound,
}

interface QuickAction {
  key: string
  label: string
  description: string
  href: string
  icon: LucideIcon
  /** Rendered only when the session holds this key (the server still decides). */
  permission?: string
}

const QUICK_ACTIONS: QuickAction[] = [
  { key: 'new-work-order', label: 'New work order', description: 'Log reactive, project or event work', href: '/work-orders/new', icon: Plus, permission: 'work_order.create' },
  { key: 'new-project', label: 'New project', description: 'Start a chapter or competition project', href: '/projects?pane=new', icon: Plus, permission: 'project.create' },
  { key: 'setup', label: 'Go to Setup Center', description: 'Chapter profile, locations, teams and more', href: '/setup', icon: Rocket },
  { key: 'notifications', label: 'Go to Notifications', description: 'Assignments, mentions and reminders', href: '/notifications', icon: Bell, permission: 'notification.read' },
]

/** A flat, navigable row: either a search hit or a quick action. */
interface PaletteRow {
  id: string
  href: string
  label: string
}

/**
 * Global search palette (Ctrl/Cmd + K and the mobile search button). Mounted
 * by the app shell; searches `GET /search` after a 200 ms debounce once two
 * characters are typed. With an empty query it offers permission-gated
 * shortcuts. Arrow keys move across groups, Enter opens, Escape closes.
 */
export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const navigate = useNavigate()
  const can = useCan()
  const listId = useId()
  const [value, setValue] = useState('')
  const [debounced, setDebounced] = useState('')
  const [active, setActive] = useState(0)
  const resultsRef = useRef<HTMLDivElement>(null)

  const query = debounced.trim()
  const enabled = query.length >= SEARCH_MIN_LENGTH
  const search = useSearch(query, { limit: SEARCH_DEFAULT_LIMIT, enabled })

  const quickActions = QUICK_ACTIONS.filter((action) => !action.permission || can(action.permission))

  const groups: SearchGroup[] = useMemo(() => (enabled && search.data ? groupSearchResults(search.data.results) : []), [enabled, search.data])
  const showActions = value.trim().length === 0
  const rows: PaletteRow[] = useMemo(() => {
    if (showActions) return quickActions.map((action) => ({ id: `${listId}-action-${action.key}`, href: action.href, label: action.label }))
    return groups.flatMap((group) => group.items.map((item) => ({ id: `${listId}-${item.key}`, href: item.href, label: item.primary })))
  }, [showActions, quickActions, groups, listId])
  const resultCount = groups.reduce((sum, group) => sum + group.items.length, 0)

  // Reset the highlight whenever the row set changes (new results, cleared query).
  const rowsKey = rows.map((row) => row.id).join('|')
  const [lastRowsKey, setLastRowsKey] = useState(rowsKey)
  if (lastRowsKey !== rowsKey) {
    setLastRowsKey(rowsKey)
    setActive(0)
  }

  // The shell unmounts the palette when it closes; if a host keeps it mounted,
  // start each opening with a clean query (adjusting state during render).
  const [wasOpen, setWasOpen] = useState(open)
  if (wasOpen !== open) {
    setWasOpen(open)
    if (open) {
      setValue('')
      setDebounced('')
      setActive(0)
    }
  }

  useEffect(() => {
    const node = resultsRef.current?.querySelector<HTMLElement>(`[data-active="true"]`)
    node?.scrollIntoView?.({ block: 'nearest' })
  }, [active, rowsKey])

  const go = useCallback(
    (href: string) => {
      onClose()
      navigate(href)
    },
    [navigate, onClose],
  )

  const onKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (rows.length) setActive((index) => (index + 1) % rows.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (rows.length) setActive((index) => (index - 1 + rows.length) % rows.length)
    } else if (event.key === 'Home' && rows.length) {
      event.preventDefault()
      setActive(0)
    } else if (event.key === 'End' && rows.length) {
      event.preventDefault()
      setActive(rows.length - 1)
    } else if (event.key === 'Enter') {
      const row = rows[active]
      if (row) {
        event.preventDefault()
        go(row.href)
      }
    } else if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    }
  }

  const activeId = rows[active]?.id
  const statusText = !showActions && value.trim().length < SEARCH_MIN_LENGTH ? `Type at least ${SEARCH_MIN_LENGTH} characters to search.` : null

  let liveMessage = ''
  if (showActions) liveMessage = `${quickActions.length} quick actions.`
  else if (statusText) liveMessage = statusText
  else if (search.isPending || search.isFetching) liveMessage = 'Searching…'
  else if (search.isError) liveMessage = 'Search failed.'
  else if (enabled && search.data) liveMessage = resultCount === 0 ? `No results for ${query}.` : `${resultCount} ${resultCount === 1 ? 'result' : 'results'} for ${query}.`

  return (
    <Dialog open={open} onClose={onClose} title="Search ASME Ops" description="Work orders, projects, assets, parts, purchase requests, locations, categories and people." size="lg">
      <div className={styles.palette}>
        <SearchField
          value={value}
          onChange={setValue}
          onDebouncedChange={setDebounced}
          debounceMs={200}
          block
          data-autofocus
          label="Search"
          placeholder="Search by name, work order number or code"
          role="combobox"
          aria-expanded={rows.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          autoComplete="off"
          onKeyDown={onKeyDown}
        />
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {liveMessage}
        </div>
        <div ref={resultsRef} className={styles.results}>
          {showActions ? (
            <div id={listId} role="listbox" aria-label="Quick actions">
              <div className={styles.group} role="group" aria-labelledby={`${listId}-actions-label`}>
                <div id={`${listId}-actions-label`} className={styles.groupLabel}>
                  Quick actions
                </div>
                {quickActions.map((action, index) => {
                  const Icon = action.icon
                  const id = `${listId}-action-${action.key}`
                  return (
                    <button
                      key={action.key}
                      type="button"
                      id={id}
                      role="option"
                      aria-selected={index === active}
                      data-active={index === active || undefined}
                      tabIndex={-1}
                      className={styles.option}
                      onMouseEnter={() => setActive(index)}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => go(action.href)}
                    >
                      <span className={styles.optionIcon} aria-hidden="true">
                        <Icon size={16} />
                      </span>
                      <span className={styles.optionBody}>
                        <span className={styles.optionPrimary}>{action.label}</span>
                        <span className={styles.optionSecondary}>{action.description}</span>
                      </span>
                      <span className={styles.optionTrailing} aria-hidden="true">
                        <ArrowRight size={14} />
                      </span>
                    </button>
                  )
                })}
                {quickActions.length === 0 && <p className={styles.status}>Type to search.</p>}
              </div>
            </div>
          ) : statusText ? (
            <p className={styles.status}>{statusText}</p>
          ) : search.isPending || (search.isFetching && !search.data) ? (
            <p className={styles.status} role="status">
              Searching…
            </p>
          ) : search.isError ? (
            <div className={styles.status} role="alert">
              <p className={styles.statusTitle}>Search is unavailable right now</p>
              <p>{errorMessage(search.error)}</p>
              <p style={{ marginTop: 'var(--space-3)' }}>
                <Button size="sm" onClick={() => void search.refetch()}>
                  Retry
                </Button>
              </p>
            </div>
          ) : resultCount === 0 ? (
            <div className={styles.status} role="status">
              <p className={styles.statusTitle}>No results for “{query}”</p>
              <p>Try a work order number, a project code or part of a name.</p>
            </div>
          ) : (
            <div id={listId} role="listbox" aria-label="Search results">
              {(() => {
                let offset = 0
                return groups.map((group) => {
                  const start = offset
                  offset += group.items.length
                  return <ResultGroup key={group.key} group={group} listId={listId} startIndex={start} active={active} onHover={setActive} onSelect={(item) => go(item.href)} />
                })
              })()}
            </div>
          )}
        </div>
        <div className={styles.footer} aria-hidden="true">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> to move
          </span>
          <span>
            <kbd>↵</kbd> to open
          </span>
          <span>
            <kbd>esc</kbd> to close
          </span>
        </div>
      </div>
    </Dialog>
  )
}

function ResultGroup({ group, listId, startIndex, active, onHover, onSelect }: { group: SearchGroup; listId: string; startIndex: number; active: number; onHover: (index: number) => void; onSelect: (item: SearchItem) => void }) {
  const Icon = GROUP_ICONS[group.key]
  const labelId = `${listId}-${group.key}-label`
  return (
    <div className={styles.group} role="group" aria-labelledby={labelId}>
      <div id={labelId} className={styles.groupLabel}>
        {group.label}
      </div>
      {group.items.map((item, offset) => {
        const index = startIndex + offset
        const selected = index === active
        return (
          <button
            key={item.key}
            type="button"
            id={`${listId}-${item.key}`}
            role="option"
            aria-selected={selected}
            data-active={selected || undefined}
            tabIndex={-1}
            className={styles.option}
            onMouseEnter={() => onHover(index)}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onSelect(item)}
          >
            <span className={styles.optionIcon} aria-hidden="true">
              {item.color ? <span className={styles.swatch} style={{ background: item.color }} /> : <Icon size={16} />}
            </span>
            <span className={styles.optionBody}>
              <span className={styles.optionPrimary}>{item.primary}</span>
              {item.secondary && <span className={styles.optionSecondary}>{item.secondary}</span>}
            </span>
            {item.status && (
              <span className={styles.optionTrailing}>
                <Badge tone="outline" size="sm">
                  {labelFor(item.status)}
                </Badge>
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export default CommandPalette
