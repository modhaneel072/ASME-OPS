import { z } from 'zod'
import { AssetRef, CategoryRef, LocationRef, ProjectRef, UserRef } from './common'

/** Limits mirrored from `asme/ops/services/search.py`. */
export const SEARCH_MIN_LENGTH = 2
export const SEARCH_DEFAULT_LIMIT = 8

/** Work-order hit from `asme/blueprints/ops/search.py::_work_order_hit`. */
export const WorkOrderHit = z.object({
  id: z.string(),
  number: z.number(),
  title: z.string(),
  status: z.string(),
  priority: z.string().nullable().optional(),
})
export type WorkOrderHit = z.infer<typeof WorkOrderHit>

export const SearchResults = z.object({
  work_orders: z.array(WorkOrderHit).default([]),
  projects: z.array(ProjectRef).default([]),
  assets: z.array(AssetRef).default([]),
  locations: z.array(LocationRef).default([]),
  categories: z.array(CategoryRef).default([]),
  users: z.array(UserRef).default([]),
})
export type SearchResults = z.infer<typeof SearchResults>

export const SearchResponse = z.object({
  query: z.string(),
  results: SearchResults,
})
export type SearchResponse = z.infer<typeof SearchResponse>

export type SearchGroupKey = keyof SearchResults

/** Display order and headings for the palette. */
export const SEARCH_GROUPS: Array<{ key: SearchGroupKey; label: string }> = [
  { key: 'work_orders', label: 'Work orders' },
  { key: 'projects', label: 'Projects' },
  { key: 'assets', label: 'Assets' },
  { key: 'locations', label: 'Locations' },
  { key: 'categories', label: 'Categories' },
  { key: 'users', label: 'People' },
]

/** One selectable row in the palette, normalised across groups. */
export interface SearchItem {
  /** Unique across the whole result set (group + id). */
  key: string
  group: SearchGroupKey
  id: string
  primary: string
  secondary?: string
  /** Router path (without the `/app` basename). */
  href: string
  /** Extra data some rows render as a badge (work-order status, asset status). */
  status?: string
  color?: string
}

export interface SearchGroup {
  key: SearchGroupKey
  label: string
  items: SearchItem[]
}

export function searchItemHref(group: SearchGroupKey, id: string | number): string {
  switch (group) {
    case 'work_orders':
      return `/work-orders/${id}`
    case 'projects':
      return `/projects/${id}`
    case 'assets':
      return `/assets/${id}`
    case 'locations':
      return `/locations/${id}`
    case 'categories':
      return `/categories/${id}`
    case 'users':
      return `/teams-users/users/${id}`
  }
}

/** Flattens the API response into ordered groups; empty groups are dropped. */
export function groupSearchResults(results: SearchResults): SearchGroup[] {
  const groups: SearchGroup[] = []
  for (const { key, label } of SEARCH_GROUPS) {
    let items: SearchItem[] = []
    switch (key) {
      case 'work_orders':
        items = results.work_orders.map((hit) => ({
          key: `work_orders:${hit.id}`,
          group: key,
          id: hit.id,
          primary: hit.title,
          secondary: `#${hit.number}`,
          status: hit.status,
          href: searchItemHref(key, hit.id),
        }))
        break
      case 'projects':
        items = results.projects.map((project) => ({
          key: `projects:${project.id}`,
          group: key,
          id: project.id,
          primary: project.name,
          secondary: project.code,
          href: searchItemHref(key, project.id),
        }))
        break
      case 'assets':
        items = results.assets.map((asset) => ({
          key: `assets:${asset.id}`,
          group: key,
          id: asset.id,
          primary: asset.name,
          secondary: asset.code ?? undefined,
          status: asset.status,
          href: searchItemHref(key, asset.id),
        }))
        break
      case 'locations':
        items = results.locations.map((location) => ({
          key: `locations:${location.id}`,
          group: key,
          id: location.id,
          primary: location.name,
          href: searchItemHref(key, location.id),
        }))
        break
      case 'categories':
        items = results.categories.map((category) => ({
          key: `categories:${category.id}`,
          group: key,
          id: category.id,
          primary: category.name,
          color: category.color,
          href: searchItemHref(key, category.id),
        }))
        break
      case 'users':
        items = results.users.map((person) => ({
          key: `users:${person.id}`,
          group: key,
          id: String(person.id),
          primary: person.name,
          secondary: person.email,
          href: searchItemHref(key, person.id),
        }))
        break
    }
    if (items.length) groups.push({ key, label, items })
  }
  return groups
}
