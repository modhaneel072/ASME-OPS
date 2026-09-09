import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type OnChangeFn, type SortingState } from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ArrowUpDown, Paperclip, UploadCloud, X } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { formatRelative } from '@/lib/dates'
import { cn } from '@/lib/cn'
import { Button } from './Button'
import { EmptyState, SkeletonRows } from './Feedback'
import styles from './data.module.css'

/* DataTable ------------------------------------------------------------------ */

export interface DataTableProps<T> {
  columns: ColumnDef<T, unknown>[]
  data: T[]
  getRowId: (row: T) => string
  sorting?: SortingState
  onSortingChange?: OnChangeFn<SortingState>
  onRowClick?: (row: T) => void
  selectedId?: string | null
  loading?: boolean
  emptyState?: ReactNode
  rowLabel?: (row: T) => string
  className?: string
}

export function DataTable<T>({ columns, data, getRowId, sorting, onSortingChange, onRowClick, selectedId, loading, emptyState, rowLabel, className }: DataTableProps<T>) {
  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: { sorting: sorting ?? [] },
    onSortingChange,
    manualSorting: true,
    enableSortingRemoval: true,
    getCoreRowModel: getCoreRowModel(),
  })

  if (loading) return <SkeletonRows rows={8} />
  if (data.length === 0) return <>{emptyState ?? <EmptyState title="Nothing here yet" compact />}</>

  return (
    <div className={cn(styles.tableWrap, className)}>
      <table className={styles.table}>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const canSort = header.column.getCanSort() && Boolean(onSortingChange)
                const sorted = header.column.getIsSorted()
                const meta = header.column.columnDef.meta as { numeric?: boolean; width?: number | string } | undefined
                return (
                  <th key={header.id} className={cn(meta?.numeric && styles.numeric)} style={{ width: meta?.width }} aria-sort={sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined}>
                    {header.isPlaceholder ? null : canSort ? (
                      <button type="button" className={styles.sortButton} onClick={header.column.getToggleSortingHandler()}>
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === 'asc' ? <ArrowUp size={12} aria-hidden="true" /> : sorted === 'desc' ? <ArrowDown size={12} aria-hidden="true" /> : <ArrowUpDown size={12} aria-hidden="true" style={{ opacity: 0.5 }} />}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const clickable = Boolean(onRowClick)
            return (
              <tr
                key={row.id}
                className={cn(clickable && styles.tableRow)}
                aria-selected={selectedId === row.id || undefined}
                tabIndex={clickable ? 0 : undefined}
                aria-label={rowLabel?.(row.original)}
                onClick={() => onRowClick?.(row.original)}
                onKeyDown={(event) => {
                  if (clickable && (event.key === 'Enter' || event.key === ' ')) {
                    event.preventDefault()
                    onRowClick?.(row.original)
                  }
                }}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as { numeric?: boolean; wrap?: boolean } | undefined
                  return (
                    <td key={cell.id} className={cn(meta?.numeric && styles.numeric, meta?.wrap && styles.wrap)}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* Pagination ------------------------------------------------------------------ */

export function LoadMore({ loaded, total, hasMore, onLoadMore, loading }: { loaded: number; total?: number; hasMore: boolean; onLoadMore: () => void; loading?: boolean }) {
  return (
    <div className={styles.pagination}>
      <span>
        Showing {loaded}
        {total !== undefined ? ` of ${total}` : ''}
      </span>
      {hasMore && (
        <Button size="sm" onClick={onLoadMore} loading={loading}>
          Load more
        </Button>
      )}
    </div>
  )
}

/* Activity timeline ----------------------------------------------------------- */

export interface TimelineItem {
  id: string
  icon?: ReactNode
  title: ReactNode
  actor?: string | null
  at: string
  content?: ReactNode
}

export function ActivityTimeline({ items, emptyText = 'No activity yet' }: { items: TimelineItem[]; emptyText?: string }) {
  if (items.length === 0) return <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-body)' }}>{emptyText}</p>
  return (
    <ol className={styles.timeline}>
      {items.map((item) => (
        <li key={item.id} className={styles.timelineItem}>
          <span className={styles.timelineIcon} aria-hidden="true">
            {item.icon ?? <span style={{ width: 6, height: 6, borderRadius: 3, background: 'currentColor' }} />}
          </span>
          <div className={styles.timelineBody}>
            <div className={styles.timelineTitle}>{item.title}</div>
            <div className={styles.timelineMeta}>
              {item.actor ? `${item.actor} · ` : ''}
              <time dateTime={item.at} title={item.at}>
                {formatRelative(item.at)}
              </time>
            </div>
            {item.content && <div className={styles.timelineContent}>{item.content}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}

/* Mentions -------------------------------------------------------------------- */

const MENTION_RE = /@\[([^\]]+)\]\(user:(\d+)\)/g

export function renderMentions(body: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let index = 0
  for (const match of body.matchAll(MENTION_RE)) {
    const start = match.index ?? 0
    if (start > last) nodes.push(body.slice(last, start))
    nodes.push(
      <span key={`m-${index++}`} className={styles.mention}>
        @{match[1]}
      </span>,
    )
    last = start + match[0].length
  }
  if (last < body.length) nodes.push(body.slice(last))
  return nodes
}

/* Comment composer ------------------------------------------------------------ */

export interface MentionCandidate {
  id: number
  name: string
}

export function CommentComposer({
  onSubmit,
  submitting,
  placeholder = 'Write a comment… use @ to mention someone',
  searchPeople,
  focusOnMount,
}: {
  onSubmit: (body: string) => Promise<void> | void
  submitting?: boolean
  placeholder?: string
  searchPeople?: (query: string) => MentionCandidate[]
  focusOnMount?: boolean
}) {
  const [value, setValue] = useState('')
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  const listId = useId()
  useEffect(() => {
    if (focusOnMount) textRef.current?.focus()
  }, [focusOnMount])
  const candidates = mentionQuery !== null && searchPeople ? searchPeople(mentionQuery).slice(0, 6) : []

  const insertMention = (person: MentionCandidate) => {
    const textarea = textRef.current
    if (!textarea) return
    const caret = textarea.selectionStart
    const before = value.slice(0, caret)
    const at = before.lastIndexOf('@')
    const token = `@[${person.name}](user:${person.id}) `
    const next = value.slice(0, at) + token + value.slice(caret)
    setValue(next)
    setMentionQuery(null)
    requestAnimationFrame(() => {
      textarea.focus()
      const position = at + token.length
      textarea.setSelectionRange(position, position)
    })
  }

  const submit = async () => {
    const body = value.trim()
    if (!body || submitting) return
    await onSubmit(body)
    setValue('')
  }

  return (
    <div className={styles.composer}>
      <textarea
        ref={textRef}
        className={styles.composerText}
        value={value}
        placeholder={placeholder}
        aria-label="Comment"
        aria-controls={candidates.length ? listId : undefined}
        onChange={(event) => {
          const next = event.target.value
          setValue(next)
          const caret = event.target.selectionStart
          const before = next.slice(0, caret)
          const match = /(^|\s)@([\w .-]{0,30})$/.exec(before)
          setMentionQuery(match && searchPeople ? match[2] : null)
        }}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault()
            void submit()
          }
          if (event.key === 'Escape' && mentionQuery !== null) setMentionQuery(null)
        }}
      />
      {candidates.length > 0 && (
        <ul id={listId} role="listbox" aria-label="People" style={{ borderTop: '1px solid var(--color-border)', padding: 4 }}>
          {candidates.map((person) => (
            <li key={person.id} role="option" aria-selected={false}>
              <button type="button" style={{ width: '100%', textAlign: 'left', padding: '6px 10px', borderRadius: 4 }} onMouseDown={(e) => e.preventDefault()} onClick={() => insertMention(person)}>
                @{person.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className={styles.composerBar}>
        <span>Ctrl/⌘ + Enter to post</span>
        <span style={{ flex: 1 }} />
        <Button variant="primary" size="sm" onClick={() => void submit()} disabled={!value.trim()} loading={submitting}>
          Comment
        </Button>
      </div>
    </div>
  )
}

/* Attachment uploader --------------------------------------------------------- */

export const UPLOAD_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'csv', 'md', 'stl', 'step', 'stp', 'gcode', '3mf', 'zip', 'xlsx', 'docx']

interface UploadEntry {
  id: number
  name: string
  status: 'uploading' | 'done' | 'error'
  error?: string
}

export function AttachmentUploader({ onUpload, maxBytes = 25 * 1024 * 1024, disabled, compact }: { onUpload: (file: File) => Promise<void>; maxBytes?: number; disabled?: boolean; compact?: boolean }) {
  const [entries, setEntries] = useState<UploadEntry[]>([])
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const counter = useRef(0)

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        const id = ++counter.current
        const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
        let error: string | undefined
        if (!UPLOAD_EXTENSIONS.includes(ext)) error = `.${ext || '?'} files are not allowed`
        else if (file.size > maxBytes) error = `Larger than ${Math.round(maxBytes / 1024 / 1024)} MB`
        else if (file.size === 0) error = 'Empty file'
        if (error) {
          setEntries((current) => [...current, { id, name: file.name, status: 'error', error }])
          continue
        }
        setEntries((current) => [...current, { id, name: file.name, status: 'uploading' }])
        try {
          await onUpload(file)
          setEntries((current) => current.filter((e) => e.id !== id))
        } catch (err) {
          setEntries((current) => current.map((e) => (e.id === id ? { ...e, status: 'error', error: (err as Error).message || 'Upload failed' } : e)))
        }
      }
    },
    [maxBytes, onUpload],
  )

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-disabled={disabled || undefined}
        className={cn(styles.dropzone, dragging && styles.dropzone_active)}
        style={compact ? { padding: 'var(--space-3)', flexDirection: 'row' } : undefined}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(event) => {
          if ((event.key === 'Enter' || event.key === ' ') && !disabled) {
            event.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          if (!disabled && event.dataTransfer.files.length) void handleFiles(event.dataTransfer.files)
        }}
      >
        <UploadCloud size={compact ? 18 : 28} aria-hidden="true" />
        <span>
          <strong>Drop files here</strong> or click to browse
        </span>
        {!compact && <span style={{ fontSize: 'var(--text-caption)' }}>Images, PDF, CAD (STL/STEP), G-code, spreadsheets · up to {Math.round(maxBytes / 1024 / 1024)} MB</span>}
        <input
          ref={inputRef}
          type="file"
          multiple
          className="sr-only"
          aria-label="Choose files"
          accept={UPLOAD_EXTENSIONS.map((e) => `.${e}`).join(',')}
          onChange={(event) => {
            if (event.target.files?.length) void handleFiles(event.target.files)
            event.target.value = ''
          }}
        />
      </div>
      {entries.length > 0 && (
        <ul className={styles.uploadList} aria-live="polite">
          {entries.map((entry) => (
            <li key={entry.id} className={styles.uploadItem}>
              <Paperclip size={14} aria-hidden="true" />
              <span className={styles.uploadName}>{entry.name}</span>
              {entry.status === 'uploading' && <span>Uploading…</span>}
              {entry.status === 'error' && <span className={styles.uploadError}>{entry.error}</span>}
              {entry.status === 'error' && (
                <button type="button" aria-label="Dismiss" onClick={() => setEntries((current) => current.filter((e) => e.id !== entry.id))}>
                  <X size={14} aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/* Report cards ----------------------------------------------------------------- */

export function ReportGrid({ children }: { children: ReactNode }) {
  return <div className={styles.reportGrid}>{children}</div>
}

export function ReportCard({ title, subtitle, value, actions, children, wide }: { title: ReactNode; subtitle?: ReactNode; value?: ReactNode; actions?: ReactNode; children?: ReactNode; wide?: boolean }) {
  return (
    <section className={cn(styles.reportCard, wide && styles.reportCard_wide)} aria-label={typeof title === 'string' ? title : undefined}>
      <header className={styles.reportHeader}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 className={styles.reportTitle}>{title}</h3>
          {subtitle && <p className={styles.reportSubtitle}>{subtitle}</p>}
          {value !== undefined && <p className={styles.reportValue}>{value}</p>}
        </div>
        {actions}
      </header>
      {children && <div className={styles.reportBody}>{children}</div>}
    </section>
  )
}

/**
 * Wraps a chart with an accessible text summary and a "show table" alternative
 * so no metric is conveyed by colour or shape alone.
 */
export function ChartFrame({ summary, table, children }: { summary: string; table: { columns: string[]; rows: Array<Array<string | number>> }; children: ReactNode }) {
  const [showTable, setShowTable] = useState(false)
  const id = useId()
  return (
    <div>
      <div className={styles.chartFrame} role="img" aria-describedby={id}>
        {showTable ? (
          <table className={styles.chartTable}>
            <thead>
              <tr>
                {table.columns.map((column, i) => (
                  <th key={column} className={cn(i > 0 && styles.numeric)}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c} className={cn(c > 0 && styles.numeric)}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          children
        )}
      </div>
      <p id={id} className="sr-only">
        {summary}
      </p>
      <div className={styles.chartToggle}>
        <Button variant="link" size="sm" onClick={() => setShowTable((s) => !s)} aria-pressed={showTable}>
          {showTable ? 'Show chart' : 'Show as table'}
        </Button>
      </div>
    </div>
  )
}
