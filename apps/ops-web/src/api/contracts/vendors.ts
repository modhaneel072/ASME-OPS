import { z } from 'zod'
import { listOf } from './common'

export const Vendor = z.looseObject({
  id: z.string(),
  name: z.string(),
  contact_name: z.string().nullable().optional(),
  email: z.string().nullable().optional(),
  phone: z.string().nullable().optional(),
  website: z.string().nullable().optional(),
  address: z.record(z.string(), z.unknown()).nullable().optional(),
  notes: z.string().nullable().optional(),
  is_active: z.boolean().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().nullable().optional(),
})
export type Vendor = z.infer<typeof Vendor>

export const VendorList = listOf(Vendor)
export type VendorList = z.infer<typeof VendorList>

/** Sort keys accepted by `GET /vendors` (`-` prefix = descending). */
export type VendorSort = 'name' | '-name' | 'created_at' | '-created_at'

export interface VendorListParams {
  q?: string
  /** `filter[active]`: the API defaults to every vendor; `all` says so explicitly. */
  active?: 'true' | 'false' | 'all'
  sort?: string
  limit?: number
  cursor?: string | null
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const WEBSITE_RE = /^https?:\/\/\S+$/i

/** Form values for the vendor pane. Blank optional text is sent as null. */
export const VendorInput = z.object({
  name: z.string().trim().min(1, 'Give the vendor a name.').max(200, 'Keep the name under 200 characters.'),
  contact_name: z.string().trim().max(160, 'Keep the contact name under 160 characters.'),
  email: z
    .string()
    .trim()
    .max(160, 'Keep the email under 160 characters.')
    .refine((value) => value === '' || EMAIL_RE.test(value), 'Enter a valid email address.'),
  phone: z.string().trim().max(40, 'Keep the phone number under 40 characters.'),
  website: z
    .string()
    .trim()
    .max(300, 'Keep the website under 300 characters.')
    .refine((value) => value === '' || WEBSITE_RE.test(value), 'Start the website with http:// or https://.'),
  notes: z.string().trim().max(5000, 'Keep the notes under 5000 characters.'),
  is_active: z.boolean(),
})
export type VendorInput = z.infer<typeof VendorInput>

/** Body sent to `POST /vendors` and `PATCH /vendors/:id`. */
export interface VendorPayload {
  name: string
  contact_name: string | null
  email: string | null
  phone: string | null
  website: string | null
  notes: string | null
  is_active: boolean
}
