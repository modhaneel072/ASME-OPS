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
