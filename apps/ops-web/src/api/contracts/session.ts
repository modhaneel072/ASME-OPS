import { z } from 'zod'
import { RoleRef, UserRef } from './common'

export const Organization = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  logo_url: z.string().nullable(),
  timezone: z.string(),
  academic_year_start_month: z.number(),
  settings: z.record(z.string(), z.unknown()),
  setup_completed_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Organization = z.infer<typeof Organization>

export const Session = z.object({
  user: UserRef.extend({
    username: z.string(),
    legacy_role: z.string(),
    major: z.string().nullable(),
    graduation_year: z.number().nullable(),
    phone: z.string().nullable().optional(),
    last_login_at: z.string().nullable(),
  }),
  organization: Organization,
  membership: z.object({
    id: z.string(),
    role: RoleRef,
    status: z.string(),
    title: z.string().nullable(),
    joined_at: z.string(),
  }),
  permissions: z.record(z.string(), z.array(z.string())),
  scope: z.object({
    project_ids: z.array(z.string()),
    team_ids: z.array(z.string()),
    lead_team_ids: z.array(z.string()),
  }),
  setup: z.object({ banner_dismissed: z.boolean(), completed: z.boolean() }),
  features: z.object({ realtime: z.string(), poll_seconds: z.number() }),
})
export type Session = z.infer<typeof Session>

export const LoginResponse = z.object({
  user: UserRef,
  session: Session.nullable().optional(),
  membership: z.null().optional(),
})
export type LoginResponse = z.infer<typeof LoginResponse>

/* Account flows ----------------------------------------------------------------
 * Signed-out password recovery and invite acceptance, plus the signed-in
 * profile and password forms. Client rules mirror the server so most mistakes
 * are caught before a request; server field errors still map onto the same keys.
 */

export const PASSWORD_MIN_LENGTH = 8
const PASSWORD_TOO_SHORT = `Use at least ${PASSWORD_MIN_LENGTH} characters.`
const PASSWORDS_DIFFER = 'The passwords do not match.'

export const ForgotPasswordResult = z.object({ sent: z.boolean() })
export type ForgotPasswordResult = z.infer<typeof ForgotPasswordResult>

export const ForgotPasswordForm = z.object({
  email: z.string().trim().min(1, 'Enter your email address.').email('Enter a valid email address.'),
})
export type ForgotPasswordForm = z.infer<typeof ForgotPasswordForm>

export const ResetTokenPurpose = z.enum(['invite', 'reset'])
export type ResetTokenPurpose = z.infer<typeof ResetTokenPurpose>

export const ResetTokenInfo = z.object({
  valid: z.boolean(),
  purpose: ResetTokenPurpose,
  email: z.string(),
  expires_at: z.string(),
})
export type ResetTokenInfo = z.infer<typeof ResetTokenInfo>

export const ResetPasswordResult = z.object({ reset: z.boolean() })
export type ResetPasswordResult = z.infer<typeof ResetPasswordResult>

export const ResetPasswordForm = z
  .object({
    password: z.string().min(PASSWORD_MIN_LENGTH, PASSWORD_TOO_SHORT),
    confirm_password: z.string().min(1, 'Enter the password again.'),
  })
  .refine((values) => values.password === values.confirm_password, { path: ['confirm_password'], message: PASSWORDS_DIFFER })
export type ResetPasswordForm = z.infer<typeof ResetPasswordForm>

export const ChangePasswordResult = z.object({ changed: z.boolean() })
export type ChangePasswordResult = z.infer<typeof ChangePasswordResult>

export const ChangePasswordForm = z
  .object({
    current_password: z.string().min(1, 'Enter your current password.'),
    new_password: z.string().min(PASSWORD_MIN_LENGTH, PASSWORD_TOO_SHORT),
    confirm_password: z.string().min(1, 'Enter the new password again.'),
  })
  .refine((values) => values.new_password === values.confirm_password, { path: ['confirm_password'], message: PASSWORDS_DIFFER })
export type ChangePasswordForm = z.infer<typeof ChangePasswordForm>

export const ProfileForm = z.object({
  name: z.string().trim().min(1, 'Enter your name.').max(160, 'Keep this under 160 characters.'),
  major: z.string().trim().max(120, 'Keep this under 120 characters.'),
  graduation_year: z
    .string()
    .trim()
    .refine((value) => value === '' || /^\d{4}$/.test(value), 'Enter a four-digit year, e.g. 2027.'),
  phone: z.string().trim().max(40, 'Keep this under 40 characters.'),
})
export type ProfileForm = z.infer<typeof ProfileForm>

export interface ProfilePatch {
  name?: string
  major?: string | null
  graduation_year?: number | null
  phone?: string | null
}

export function profileToForm(user: Session['user']): ProfileForm {
  return {
    name: user.name,
    major: user.major ?? '',
    graduation_year: user.graduation_year ? String(user.graduation_year) : '',
    phone: user.phone ?? '',
  }
}

/**
 * Builds the PATCH body from only the fields the person changed, so a value the
 * session payload does not carry is never overwritten. Cleared optional fields
 * are sent as null.
 */
export function toProfilePatch(values: ProfileForm, dirty: Partial<Record<keyof ProfileForm, boolean | undefined>>): ProfilePatch {
  const patch: ProfilePatch = {}
  if (dirty.name) patch.name = values.name.trim()
  if (dirty.major) patch.major = values.major.trim() || null
  if (dirty.graduation_year) patch.graduation_year = values.graduation_year.trim() ? Number(values.graduation_year.trim()) : null
  if (dirty.phone) patch.phone = values.phone.trim() || null
  return patch
}

export const ProfileUpdateResult = z.object({ session: Session })
export type ProfileUpdateResult = z.infer<typeof ProfileUpdateResult>
