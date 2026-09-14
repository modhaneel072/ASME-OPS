import { z } from 'zod'
import { listOf, UserRef } from './common'

export const Category = z.looseObject({
  id: z.string(),
  name: z.string(),
  color: z.string(),
  icon: z.string(),
  description: z.string().nullable().optional(),
  usage: z.object({ work_orders: z.number() }).optional(),
  created_at: z.string().optional(),
  updated_at: z.string().nullable().optional(),
  created_by: UserRef.nullable().optional(),
})
export type Category = z.infer<typeof Category>

export const CategoryList = listOf(Category)
export type CategoryList = z.infer<typeof CategoryList>

/** Sort keys accepted by `GET /categories` (`-` prefix = descending). */
export type CategorySort = 'name' | '-name' | 'usage' | '-usage' | 'created_at' | '-created_at'

export interface CategoryListParams {
  q?: string
  sort?: string
  limit?: number
  cursor?: string | null
}

/** Mirrors `HEX_COLOR_RE` in `asme/ops/validation.py`. */
export const HEX_COLOR_RE = /^#[0-9a-fA-F]{6}$/

export const DEFAULT_CATEGORY_COLOR = '#0878d1'
export const DEFAULT_CATEGORY_ICON = 'tag'

/** Form values for the create/edit pane. Blank description is sent as null. */
export const CategoryInput = z.object({
  name: z.string().trim().min(1, 'Give the category a name.').max(120, 'Keep the name under 120 characters.'),
  color: z.string().trim().regex(HEX_COLOR_RE, 'Use a six-digit hex colour such as #0878d1.'),
  icon: z.string().trim().min(1, 'Choose an icon.').max(60, 'Icon names are limited to 60 characters.'),
  description: z.string().trim().max(2000, 'Keep the description under 2000 characters.'),
})
export type CategoryInput = z.infer<typeof CategoryInput>

/** Body sent to `POST /categories` and `PATCH /categories/:id`. */
export interface CategoryPayload {
  name: string
  color: string
  icon: string
  description: string | null
}

/**
 * Preset swatches offered in the colour picker. These are category data
 * values stored on the server (the seed categories use them), not UI chrome;
 * any other six-digit hex can still be typed into the hex field.
 */
export const CATEGORY_COLOR_PRESETS: ReadonlyArray<{ hex: string; name: string }> = [
  { hex: '#0878d1', name: 'Iowa blue' },
  { hex: '#ffcd00', name: 'Iowa gold' },
  { hex: '#e58a00', name: 'Amber' },
  { hex: '#b45309', name: 'Rust' },
  { hex: '#d84a4a', name: 'Red' },
  { hex: '#9f1239', name: 'Crimson' },
  { hex: '#00a878', name: 'Green' },
  { hex: '#0f766e', name: 'Teal' },
  { hex: '#0e7490', name: 'Cyan' },
  { hex: '#7c5ce7', name: 'Violet' },
  { hex: '#c026d3', name: 'Magenta' },
  { hex: '#475569', name: 'Slate' },
]
