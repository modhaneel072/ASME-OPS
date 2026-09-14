import { z } from 'zod'
import { listOf, ProjectRef, UserRef } from './common'

export const Team = z.looseObject({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  parent_team_id: z.string().nullable().optional(),
  project: ProjectRef.nullable().optional(),
  leads: z.array(UserRef).default([]),
  member_count: z.number().optional(),
  is_active: z.boolean().optional(),
  created_at: z.string().optional(),
})
export type Team = z.infer<typeof Team>

export const TeamList = listOf(Team)

export interface TeamListParams {
  q?: string
  project?: string[]
  active?: 'true' | 'false'
  sort?: string
  limit?: number
  cursor?: string | null
}

/* ---- Teams / Users feature ------------------------------------------------- */

/** One entry of `team_detail.members` (asme/ops/serializers/teams.py::team_member). Leads come first. */
export const TeamMember = z.object({
  user: UserRef,
  is_lead: z.boolean(),
  joined_at: z.string().nullable().optional(),
})
export type TeamMember = z.infer<typeof TeamMember>

/** `GET|POST|PATCH /teams/:id` and `PUT /teams/:id/members` all answer with this shape under `payload.team`. */
export const TeamDetail = Team.extend({ members: z.array(TeamMember).default([]) })
export type TeamDetail = z.infer<typeof TeamDetail>

/** Create / edit form values; mirrors CREATE_SPEC / UPDATE_SPEC in asme/ops/services/teams.py. */
export const TeamInput = z.object({
  name: z.string().trim().min(1, 'Give the team a name.').max(160, 'Keep the name under 160 characters.'),
  description: z.string().trim().max(4000, 'Keep the description under 4,000 characters.').optional().or(z.literal('')),
  parent_team_id: z.string().nullable().optional(),
  project_id: z.string().nullable().optional(),
})
export type TeamInput = z.infer<typeof TeamInput>

/** One row of the `PUT /teams/:id/members` body. */
export interface TeamMemberInput {
  user_id: number
  is_lead: boolean
}

/** Body of `PUT /teams/:id/members`; replaces the whole membership. */
export interface TeamMembersInput {
  members: TeamMemberInput[]
}

/** Sorts accepted by `GET /teams` (services/teams.py::SORTS with the optional `-` prefix). */
export const TEAM_SORTS = ['name', '-name', 'created_at', '-created_at'] as const
export type TeamSort = (typeof TEAM_SORTS)[number]
