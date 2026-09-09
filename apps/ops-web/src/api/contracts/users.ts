import { z } from 'zod'
import { listOf, RoleRef, TeamRef, UserRef } from './common'

/**
 * `user_ref` plus optional account fields. The API's `user_ref` carries only
 * id/name/email/avatar today; `username` and `legacy_role` are known for the
 * session user (from `/session`) and will be read from here if the directory
 * ever adds them.
 */
export const MemberUser = UserRef.extend({
  username: z.string().nullable().optional(),
  legacy_role: z.string().nullable().optional(),
})
export type MemberUser = z.infer<typeof MemberUser>

/** Directory entry (`member(user)` shape from asme/ops/serializers/users.py). Loose so the owning feature can extend it. */
export const Member = z.looseObject({
  id: z.string(),
  user: MemberUser,
  role: RoleRef,
  status: z.string(),
  teams: z.array(TeamRef).default([]),
  joined_at: z.string().nullable().optional(),
  last_login_at: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
})
export type Member = z.infer<typeof Member>

export const MemberList = listOf(Member)

export const Role = z.looseObject({
  id: z.string(),
  name: z.string(),
  system_key: z.string().nullable(),
  is_custom: z.boolean().optional(),
  description: z.string().nullable().optional(),
  member_count: z.number().optional(),
  grants: z.array(z.object({ key: z.string(), scope: z.string() })).optional(),
})
export type Role = z.infer<typeof Role>

export interface UserListParams {
  q?: string
  role?: string[]
  status?: string[]
  team?: string[]
  sort?: string
  limit?: number
  cursor?: string | null
}

/* ---- Teams / Users feature ------------------------------------------------- */

/** `ops_memberships.member_status` values (asme/ops/models/identity.py::MEMBER_STATUSES). */
export const MEMBER_STATUSES = ['active', 'invited', 'suspended'] as const
export type MemberStatus = (typeof MEMBER_STATUSES)[number]

/** Statuses `PATCH /users/:id` accepts (services/users.py::PATCHABLE_STATUSES). */
export const PATCHABLE_STATUSES = ['active', 'suspended'] as const
export type PatchableStatus = (typeof PATCHABLE_STATUSES)[number]

/** Sorts accepted by `GET /users` (services/users.py::SORTS with the optional `-` prefix). */
export const USER_SORTS = ['name', '-name', 'joined_at', '-joined_at', 'last_login_at', '-last_login_at'] as const
export type UserSort = (typeof USER_SORTS)[number]

/** Invite form values; mirrors INVITE_SPEC in asme/ops/services/users.py. */
export const InviteInput = z.object({
  email: z.email('Enter a valid email address.').max(160, 'Keep the email under 160 characters.'),
  name: z.string().trim().min(2, 'Enter the member’s full name.').max(160, 'Keep the name under 160 characters.'),
  role_key: z.string().min(1, 'Choose a role.'),
  title: z.string().trim().max(120, 'Keep the title under 120 characters.').optional().or(z.literal('')),
})
export type InviteInput = z.infer<typeof InviteInput>

/** Body of `POST /users/invite`. */
export interface InviteRequest {
  email: string
  name: string
  role_key: string
  title?: string
}

/** `POST /users/invite` payload. The link is returned exactly once. */
export const InviteResult = z.object({ member: Member, invite_url: z.string() })
export type InviteResult = z.infer<typeof InviteResult>

/** "Role & access" card values. */
export const MemberAccessInput = z.object({
  role_id: z.string().min(1, 'Choose a role.'),
  status: z.enum(MEMBER_STATUSES),
  title: z.string().trim().max(120, 'Keep the title under 120 characters.').optional().or(z.literal('')),
})
export type MemberAccessInput = z.infer<typeof MemberAccessInput>

/** Body of `PATCH /users/:id`; only changed keys are sent (an empty body is a validation error). */
export interface MemberUpdateInput {
  role_id?: string
  role_key?: string
  status?: PatchableStatus
  title?: string | null
}
