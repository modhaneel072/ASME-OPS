import { ChevronRight } from 'lucide-react'
import { useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import type { AssetHierarchyNode } from '@/api/contracts/assets'
import styles from './assets.module.css'
import { StatusText, TypeChips } from './bits'
import { ancestorsOf, collectIds, flattenTree } from './params'

export interface AssetTreeProps {
  nodes: AssetHierarchyNode[]
  selectedId?: string | null
  onOpen: (asset: AssetHierarchyNode) => void
  label?: string
}

/**
 * Accessible tree (WAI-ARIA tree pattern with roving tabindex). Expanded state
 * lives here; ancestors of the selected asset are expanded automatically so a
 * deep link lands on a visible row.
 */
export function AssetTree({ nodes, selectedId, onOpen, label = 'Asset hierarchy' }: AssetTreeProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => collectIds(nodes))
  const [seenRoots, setSeenRoots] = useState(nodes)
  if (seenRoots !== nodes) {
    // New data: keep what the user collapsed, expand anything new.
    const previous = collectIds(seenRoots)
    setSeenRoots(nodes)
    setExpanded((current) => {
      const next = new Set(current)
      for (const id of collectIds(nodes)) if (!previous.has(id)) next.add(id)
      return next
    })
  }

  // Deep links: expand the ancestors of the selected asset so its row is visible.
  const [revealed, setRevealed] = useState<string | null>(null)
  const revealKey = selectedId ? `${selectedId}|${nodes.length}` : null
  if (revealKey !== revealed) {
    setRevealed(revealKey)
    const trail = selectedId ? ancestorsOf(nodes, selectedId) : null
    if (trail?.length && !trail.every((id) => expanded.has(id))) {
      const next = new Set(expanded)
      trail.forEach((id) => next.add(id))
      setExpanded(next)
    }
  }

  const rows = useMemo(() => flattenTree(nodes, expanded), [nodes, expanded])
  const [focusId, setFocusId] = useState<string | null>(null)
  const activeId = rows.some((r) => r.node.id === focusId) ? focusId : rows.some((r) => r.node.id === selectedId) ? selectedId! : (rows[0]?.node.id ?? null)
  const itemRefs = useRef(new Map<string, HTMLDivElement>())

  const focusRow = (id: string | undefined) => {
    if (!id) return
    setFocusId(id)
    itemRefs.current.get(id)?.focus()
  }

  const toggle = (id: string, open?: boolean) => {
    setExpanded((current) => {
      const next = new Set(current)
      const shouldOpen = open ?? !next.has(id)
      if (shouldOpen) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>, index: number) => {
    const row = rows[index]
    if (!row) return
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        focusRow(rows[index + 1]?.node.id)
        break
      case 'ArrowUp':
        event.preventDefault()
        focusRow(rows[index - 1]?.node.id)
        break
      case 'ArrowRight':
        event.preventDefault()
        if (row.hasChildren && !expanded.has(row.node.id)) toggle(row.node.id, true)
        else if (row.hasChildren) focusRow(rows[index + 1]?.node.id)
        break
      case 'ArrowLeft':
        event.preventDefault()
        if (row.hasChildren && expanded.has(row.node.id)) toggle(row.node.id, false)
        else if (row.parentId) focusRow(row.parentId)
        break
      case 'Home':
        event.preventDefault()
        focusRow(rows[0]?.node.id)
        break
      case 'End':
        event.preventDefault()
        focusRow(rows[rows.length - 1]?.node.id)
        break
      case 'Enter':
      case ' ':
        event.preventDefault()
        onOpen(row.node)
        break
      default:
        break
    }
  }

  return (
    <div role="tree" aria-label={label} className={styles.tree}>
      {rows.map(({ node, depth, hasChildren }, index) => {
        const isExpanded = hasChildren ? expanded.has(node.id) : undefined
        const selected = node.id === selectedId
        return (
          <div
            key={node.id}
            ref={(el) => {
              if (el) itemRefs.current.set(node.id, el)
              else itemRefs.current.delete(node.id)
            }}
            role="treeitem"
            aria-level={depth + 1}
            aria-expanded={isExpanded}
            aria-selected={selected}
            tabIndex={node.id === activeId ? 0 : -1}
            className={styles.treeItem}
            style={{ '--depth': depth } as CSSProperties}
            data-testid="asset-tree-item"
            onClick={() => onOpen(node)}
            onFocus={() => setFocusId(node.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {hasChildren ? (
              <button
                type="button"
                className={styles.treeToggle}
                tabIndex={-1}
                aria-expanded={isExpanded}
                aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${node.name}`}
                onClick={(event) => {
                  event.stopPropagation()
                  toggle(node.id)
                }}
              >
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            ) : (
              <span className={styles.treeSpacer} aria-hidden="true" />
            )}
            <span className={styles.treeBody}>
              <span className={styles.treeName}>
                <span>{node.name}</span>
                {node.code && <span className={styles.code}>{node.code}</span>}
              </span>
              <span className={styles.treeMeta}>
                <StatusText status={node.status} />
                {node.types.length > 0 && <TypeChips types={node.types} max={2} />}
              </span>
            </span>
            {(node.open_work_order_count ?? 0) > 0 && <span className={styles.treeCount}>{node.open_work_order_count} open work</span>}
          </div>
        )
      })}
    </div>
  )
}
