import { ASSET_SORTS, type AssetHierarchyNode, type AssetSort } from '@/api/contracts/assets'

export type AssetView = 'panel' | 'table' | 'hierarchy'
export const ASSET_VIEWS: AssetView[] = ['panel', 'table', 'hierarchy']

export const FILTER_KEYS = ['status', 'criticality', 'type', 'project', 'location', 'team'] as const
export type FilterKey = (typeof FILTER_KEYS)[number]
export type AssetFilters = Record<FilterKey, string[]>

export function readView(params: URLSearchParams): AssetView {
  const raw = params.get('view')
  return (ASSET_VIEWS as string[]).includes(raw ?? '') ? (raw as AssetView) : 'panel'
}

export function readSort(params: URLSearchParams): AssetSort {
  const raw = params.get('sort')
  return (ASSET_SORTS as readonly string[]).includes(raw ?? '') ? (raw as AssetSort) : 'name'
}

/** `filter[status]=a,b` → `['a','b']`; repeated keys are merged like the server does. */
export function readFilters(params: URLSearchParams): AssetFilters {
  const filters = {} as AssetFilters
  for (const key of FILTER_KEYS) {
    const values = params
      .getAll(`filter[${key}]`)
      .flatMap((raw) => raw.split(','))
      .map((v) => v.trim())
      .filter(Boolean)
    filters[key] = Array.from(new Set(values))
  }
  return filters
}

export function hasActiveFilters(filters: AssetFilters): boolean {
  return FILTER_KEYS.some((key) => filters[key].length > 0)
}

export function writeFilter(params: URLSearchParams, key: FilterKey, values: string[]): URLSearchParams {
  const next = new URLSearchParams(params)
  next.delete(`filter[${key}]`)
  if (values.length) next.set(`filter[${key}]`, values.join(','))
  return next
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const key of FILTER_KEYS) next.delete(`filter[${key}]`)
  next.delete('q')
  return next
}

/** Search string carried between list and detail links (drops pane state). */
export function listSearch(params: URLSearchParams): string {
  const next = new URLSearchParams(params)
  next.delete('pane')
  next.delete('parent')
  const text = next.toString()
  return text ? `?${text}` : ''
}

/* Hierarchy helpers ------------------------------------------------------------ */

export interface FlatNode {
  node: AssetHierarchyNode
  depth: number
  parentId: string | null
  hasChildren: boolean
}

/** Keeps nodes that match `predicate` or have a matching descendant (ancestors stay for context). */
export function pruneTree(nodes: AssetHierarchyNode[], predicate: (node: AssetHierarchyNode) => boolean): AssetHierarchyNode[] {
  const out: AssetHierarchyNode[] = []
  for (const node of nodes) {
    const children = pruneTree(node.children ?? [], predicate)
    if (predicate(node) || children.length) out.push({ ...node, children })
  }
  return out
}

/** Depth-first list of visible rows given the expanded set. */
export function flattenTree(nodes: AssetHierarchyNode[], expanded: Set<string>, depth = 0, parentId: string | null = null, out: FlatNode[] = []): FlatNode[] {
  for (const node of nodes) {
    const children = node.children ?? []
    out.push({ node, depth, parentId, hasChildren: children.length > 0 })
    if (children.length && expanded.has(node.id)) flattenTree(children, expanded, depth + 1, node.id, out)
  }
  return out
}

export function collectIds(nodes: AssetHierarchyNode[], out = new Set<string>()): Set<string> {
  for (const node of nodes) {
    if (node.children?.length) {
      out.add(node.id)
      collectIds(node.children, out)
    }
  }
  return out
}

/** Ids of every ancestor of `id` inside the forest. */
export function ancestorsOf(nodes: AssetHierarchyNode[], id: string, trail: string[] = []): string[] | null {
  for (const node of nodes) {
    if (node.id === id) return trail
    const found = ancestorsOf(node.children ?? [], id, [...trail, node.id])
    if (found) return found
  }
  return null
}

export function matchesSearch(node: { name: string; code?: string | null; serial_number?: string | null; manufacturer?: string | null; model?: string | null }, needle: string): boolean {
  const q = needle.trim().toLowerCase()
  if (!q) return true
  return [node.name, node.code, node.serial_number, node.manufacturer, node.model].some((value) => value?.toLowerCase().includes(q))
}
