import { z } from 'zod'
import { TeamRef, UserRef } from './common'

export const SAVED_FILTER_VISIBILITIES = ['private', 'team', 'chapter'] as const
export type SavedFilterVisibility = (typeof SAVED_FILTER_VISIBILITIES)[number]
export const SAVED_FILTER_VISIBILITY_LABELS: Record<SavedFilterVisibility, string> = { private: 'Only me', team: 'A team', chapter: 'Whole chapter' }

export type SavedFilterEntity = 'work_order' | 'project' | 'asset'

/** Shape from asme/ops/serializers/saved_filters.py. `filter` is a flat map of list parameters. */
export const SavedFilter = z.looseObject({
  id: z.string(),
  entity_type: z.string(),
  name: z.string(),
  visibility: z.string(),
  team: TeamRef.nullable().optional(),
  owner: UserRef.nullable().optional(),
  filter: z.record(z.string(), z.unknown()).default({}),
  sort: z.unknown().nullable().optional(),
  view_type: z.string().nullable().optional(),
  is_default: z.boolean().default(false),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
})
export type SavedFilter = z.infer<typeof SavedFilter>

export const SavedFilterLists = z.object({ personal: z.array(SavedFilter).default([]), shared: z.array(SavedFilter).default([]) })
export type SavedFilterLists = z.infer<typeof SavedFilterLists>

export interface SavedFilterInput {
  entity_type: SavedFilterEntity
  name: string
  visibility?: SavedFilterVisibility
  team_id?: string | null
  filter: Record<string, string>
  sort?: string | null
  view_type?: string | null
  is_default?: boolean
}

export type SavedFilterPatch = Partial<Omit<SavedFilterInput, 'entity_type'>>

export const SavedFilterNameInput = z.object({
  name: z.string().trim().min(1, 'Give the filter a name.').max(120, 'Keep the name under 120 characters.'),
})

export const SavedFilterShareInput = z
  .object({
    visibility: z.enum(SAVED_FILTER_VISIBILITIES),
    team_id: z.string().nullable(),
  })
  .refine((value) => value.visibility !== 'team' || Boolean(value.team_id), { message: 'Choose the team to share this filter with.', path: ['team_id'] })
export type SavedFilterShareInput = z.infer<typeof SavedFilterShareInput>
