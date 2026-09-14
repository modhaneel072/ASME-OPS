import { z } from 'zod'
import { listOf } from './common'

export const Location = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  parent_id: z.string().nullable(),
  building: z.string().nullable(),
  room: z.string().nullable(),
  is_default: z.boolean(),
  path: z.array(z.string()),
  asset_count: z.number().optional().default(0),
  open_work_order_count: z.number().optional().default(0),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Location = z.infer<typeof Location>

export const LocationList = listOf(Location)
export type LocationList = z.infer<typeof LocationList>

export interface LocationTreeNode extends Location {
  children: LocationTreeNode[]
}

export const LocationInput = z.object({
  name: z.string().trim().min(1, 'Give the location a name.').max(160, 'Keep the name under 160 characters.'),
  description: z.string().trim().max(2000).optional().or(z.literal('')),
  parent_id: z.string().nullable().optional(),
  building: z.string().trim().max(160).optional().or(z.literal('')),
  room: z.string().trim().max(80).optional().or(z.literal('')),
})
export type LocationInput = z.infer<typeof LocationInput>

export interface LocationListParams {
  q?: string
  parent?: string
  active?: 'true' | 'false'
  sort?: 'name' | '-name' | 'created_at' | '-created_at'
  limit?: number
  cursor?: string | null
}
