import { z } from 'zod'
import { Organization } from './session'

export { Organization }

/** Keys the server accepts under `settings` (`asme/ops/services/organizations.py::ALLOWED_SETTINGS`). */
export const ChapterSettings = z.object({
  profile_completed: z.boolean().optional(),
  chapter_short_name: z.string().nullable().optional(),
  primary_contact_email: z.string().nullable().optional(),
  public_site_url: z.string().nullable().optional(),
  default_due_days: z.number().nullable().optional(),
})
export type ChapterSettings = z.infer<typeof ChapterSettings>

/** Body for `PATCH /organization` (all keys optional; `settings` is merged server-side). */
export interface OrganizationPatch {
  name?: string
  timezone?: string
  academic_year_start_month?: number
  logo_url?: string | null
  settings?: ChapterSettings
}

const HTTP_URL = /^https?:\/\/\S+$/i
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const optionalUrl = z
  .string()
  .trim()
  .max(500, 'Keep the URL under 500 characters.')
  .refine((value) => value === '' || HTTP_URL.test(value), 'Enter a full URL starting with http:// or https://.')

/**
 * Chapter settings form. Every field is kept as a string/boolean so the form
 * types match the inputs; `toOrganizationPatch` converts to the API body.
 */
export const ChapterSettingsForm = z.object({
  name: z.string().trim().min(2, 'Give the chapter a name (at least 2 characters).').max(200, 'Keep the name under 200 characters.'),
  timezone: z.string().trim().min(1, 'Choose a time zone.').max(64, 'Keep the time zone under 64 characters.'),
  academic_year_start_month: z
    .string()
    .refine((value) => /^\d+$/.test(value) && Number(value) >= 1 && Number(value) <= 12, 'Choose the month the academic year starts.'),
  logo_url: optionalUrl,
  profile_completed: z.boolean(),
  chapter_short_name: z.string().trim().max(40, 'Keep the short name under 40 characters.'),
  primary_contact_email: z
    .string()
    .trim()
    .max(160)
    .refine((value) => value === '' || EMAIL.test(value), 'Enter a valid email address.'),
  public_site_url: optionalUrl,
  default_due_days: z.string().trim().refine((value) => value === '' || (/^\d+$/.test(value) && Number(value) <= 365), 'Enter a whole number of days (0–365).'),
})
export type ChapterSettingsForm = z.infer<typeof ChapterSettingsForm>

export function organizationToForm(org: Organization): ChapterSettingsForm {
  const settings = org.settings as Record<string, unknown>
  const dueDays = settings.default_due_days
  return {
    name: org.name,
    timezone: org.timezone,
    academic_year_start_month: String(org.academic_year_start_month),
    logo_url: org.logo_url ?? '',
    profile_completed: settings.profile_completed === true,
    chapter_short_name: typeof settings.chapter_short_name === 'string' ? settings.chapter_short_name : '',
    primary_contact_email: typeof settings.primary_contact_email === 'string' ? settings.primary_contact_email : '',
    public_site_url: typeof settings.public_site_url === 'string' ? settings.public_site_url : '',
    default_due_days: typeof dueDays === 'number' ? String(dueDays) : typeof dueDays === 'string' ? dueDays : '',
  }
}

export function toOrganizationPatch(values: ChapterSettingsForm): OrganizationPatch {
  return {
    name: values.name,
    timezone: values.timezone,
    academic_year_start_month: Number(values.academic_year_start_month),
    logo_url: values.logo_url || null,
    settings: {
      profile_completed: values.profile_completed,
      chapter_short_name: values.chapter_short_name || null,
      primary_contact_email: values.primary_contact_email || null,
      public_site_url: values.public_site_url || null,
      default_due_days: values.default_due_days === '' ? null : Number(values.default_due_days),
    },
  }
}

/** Server error keys → form fields. `settings` errors land on the form root. */
export const ORGANIZATION_FIELD_MAP: Record<string, keyof ChapterSettingsForm> = {
  name: 'name',
  timezone: 'timezone',
  academic_year_start_month: 'academic_year_start_month',
  logo_url: 'logo_url',
}

export const MONTHS = [
  { value: '1', label: 'January' },
  { value: '2', label: 'February' },
  { value: '3', label: 'March' },
  { value: '4', label: 'April' },
  { value: '5', label: 'May' },
  { value: '6', label: 'June' },
  { value: '7', label: 'July' },
  { value: '8', label: 'August' },
  { value: '9', label: 'September' },
  { value: '10', label: 'October' },
  { value: '11', label: 'November' },
  { value: '12', label: 'December' },
] as const

export function monthLabel(month: number | string): string {
  return MONTHS.find((m) => m.value === String(month))?.label ?? String(month)
}

/** Common IANA zones for the picker; anything else is typed in. */
export const COMMON_TIMEZONES = [
  'America/Chicago',
  'America/New_York',
  'America/Denver',
  'America/Phoenix',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'America/Toronto',
  'America/Mexico_City',
  'America/Sao_Paulo',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Madrid',
  'Africa/Johannesburg',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Australia/Sydney',
  'UTC',
] as const

export const CUSTOM_TIMEZONE = '__custom__'
