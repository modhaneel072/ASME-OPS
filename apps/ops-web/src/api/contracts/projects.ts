import { z } from 'zod'
import { AuditEvent, listOf, TeamRef, UserRef } from './common'

export const Milestone = z.looseObject({
  id: z.string(),
  project_id: z.string().optional(),
  name: z.string(),
  description: z.string().nullable().optional(),
  due_date: z.string().nullable().optional(),
  status: z.string(),
  owner: UserRef.nullable().optional(),
  weight: z.number().optional(),
  completed_at: z.string().nullable().optional(),
  order_index: z.number().optional(),
})
export type Milestone = z.infer<typeof Milestone>

export const Project = z.looseObject({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  description: z.string().nullable().optional(),
  status: z.string(),
  visibility: z.string(),
  risk_level: z.string().optional(),
  lead: UserRef.nullable().optional(),
  faculty_advisor: UserRef.nullable().optional(),
  start_date: z.string().nullable().optional(),
  target_date: z.string().nullable().optional(),
  budget_amount: z.number().nullable().optional(),
  repository_url: z.string().nullable().optional(),
  cad_url: z.string().nullable().optional(),
  requirements_url: z.string().nullable().optional(),
  competition: z.string().nullable().optional(),
  academic_year: z.string().nullable().optional(),
  public_project_id: z.number().nullable().optional(),
  archived_at: z.string().nullable().optional(),
  stats: z
    .looseObject({
      open_work_orders: z.number().optional(),
      overdue_work_orders: z.number().optional(),
      completion_percent: z.number().optional(),
      next_milestone: Milestone.nullable().optional(),
      member_count: z.number().optional(),
    })
    .optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
})
export type Project = z.infer<typeof Project>

export const ProjectList = listOf(Project)

export interface ProjectListParams {
  view?: 'active' | 'all' | 'archived'
  q?: string
  lead?: string[]
  status?: string[]
  risk?: string[]
  team?: string[]
  academic_year?: string[]
  competition?: string
  sort?: string
  limit?: number
  cursor?: string | null
}

/* Enumerations (mirror asme/ops/models/projects.py) ------------------------ */

export const PROJECT_STATUSES = ['planning', 'active', 'on_hold', 'completed'] as const
export type ProjectStatus = (typeof PROJECT_STATUSES)[number]
export const PROJECT_VISIBILITIES = ['chapter', 'private'] as const
export type ProjectVisibility = (typeof PROJECT_VISIBILITIES)[number]
export const RISK_LEVELS = ['low', 'medium', 'high', 'critical'] as const
export type RiskLevel = (typeof RISK_LEVELS)[number]
export const PROJECT_ROLES = ['lead', 'member', 'advisor', 'viewer'] as const
export type ProjectRole = (typeof PROJECT_ROLES)[number]
export const MILESTONE_STATUSES = ['planned', 'in_progress', 'done', 'missed'] as const
export type MilestoneStatus = (typeof MILESTONE_STATUSES)[number]

export const RISK_LABELS: Record<RiskLevel, string> = { low: 'Low risk', medium: 'Medium risk', high: 'High risk', critical: 'Critical risk' }
export const PROJECT_ROLE_LABELS: Record<ProjectRole, string> = { lead: 'Lead', member: 'Member', advisor: 'Advisor', viewer: 'Viewer' }

/* Members ------------------------------------------------------------------- */

export const ProjectMember = z.looseObject({
  user: UserRef,
  project_role: z.string(),
  team: TeamRef.nullable().optional(),
  joined_at: z.string().nullable().optional(),
})
export type ProjectMember = z.infer<typeof ProjectMember>

/** `GET /projects/:id` returns the project plus its members. */
export const ProjectDetail = z.object({ project: Project, members: z.array(ProjectMember).default([]) })
export type ProjectDetail = z.infer<typeof ProjectDetail>

export const MemberInput = z.object({
  user_id: z.number(),
  project_role: z.enum(PROJECT_ROLES),
  team_id: z.string().nullable().optional(),
})
export type MemberInput = z.infer<typeof MemberInput>

export const MembersInput = z.object({ members: z.array(MemberInput) })
export type MembersInput = z.infer<typeof MembersInput>

/* Health -------------------------------------------------------------------- */

export const ProjectHealth = z.looseObject({
  completion_percent: z.number(),
  work: z.looseObject({
    total: z.number(),
    open: z.number(),
    in_progress: z.number(),
    on_hold: z.number(),
    done: z.number(),
    canceled: z.number(),
    overdue: z.number(),
    blocked: z.number(),
  }),
  milestones: z.looseObject({
    total: z.number(),
    done: z.number(),
    missed: z.number(),
    upcoming: z.array(Milestone).default([]),
  }),
  budget: z.looseObject({
    amount: z.number().nullable(),
    used: z.number(),
    remaining: z.number().nullable(),
  }),
  members: z.number(),
  teams: z.array(TeamRef).default([]),
  activity_7d: z.number(),
})
export type ProjectHealth = z.infer<typeof ProjectHealth>

export const MilestoneList = listOf(Milestone)
export const ActivityList = listOf(AuditEvent)
export type ActivityList = z.infer<typeof ActivityList>

/* Attachments (asme/ops/serializers/attachments.py) ------------------------- */

export const Attachment = z.looseObject({
  id: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  original_name: z.string(),
  content_type: z.string().nullable().optional(),
  size_bytes: z.number(),
  is_image: z.boolean().optional(),
  uploaded_by: UserRef.nullable(),
  download_url: z.string(),
  created_at: z.string(),
})
export type Attachment = z.infer<typeof Attachment>
export const AttachmentList = listOf(Attachment)

/* Work-order rows shown on the Work tab (subset of the work_order shape) ---- */

export const ProjectWorkOrderRow = z.looseObject({
  id: z.string(),
  number: z.number(),
  title: z.string(),
  status: z.string(),
  priority: z.string().nullable().optional(),
  assignees: z.array(UserRef).default([]),
  due_at: z.string().nullable().optional(),
  is_overdue: z.boolean().optional(),
  updated_at: z.string().optional(),
})
export type ProjectWorkOrderRow = z.infer<typeof ProjectWorkOrderRow>
export const ProjectWorkOrderList = listOf(ProjectWorkOrderRow)

/* Form schemas --------------------------------------------------------------- */

const optionalText = (max: number, message?: string) => z.string().trim().max(max, message).optional().or(z.literal(''))
const optionalUrl = z
  .string()
  .trim()
  .max(500, 'Keep the link under 500 characters.')
  .refine((value) => !value || /^https?:\/\/\S+$/i.test(value), 'Enter a full link starting with http:// or https://.')
  .optional()
  .or(z.literal(''))

/** Form values for the create/edit pane. Empty strings mean "not set". */
export const ProjectInput = z
  .object({
    name: z.string().trim().min(1, 'Give the project a name.').max(200, 'Keep the name under 200 characters.'),
    code: z
      .string()
      .trim()
      .max(20, 'Codes are at most 20 characters.')
      .refine((value) => !value || /^[A-Za-z0-9][A-Za-z0-9_-]{0,19}$/.test(value), 'Use up to 20 letters, digits, dashes or underscores.')
      .optional()
      .or(z.literal('')),
    description: optionalText(5000),
    status: z.enum(PROJECT_STATUSES),
    visibility: z.enum(PROJECT_VISIBILITIES),
    risk_level: z.enum(RISK_LEVELS),
    lead_user_id: z.number().nullable(),
    faculty_advisor_user_id: z.number().nullable(),
    start_date: z.string().optional().or(z.literal('')),
    target_date: z.string().optional().or(z.literal('')),
    budget_amount: z
      .string()
      .trim()
      .refine((value) => !value || (!Number.isNaN(Number(value)) && Number(value) >= 0), 'Enter a budget of zero or more.')
      .optional()
      .or(z.literal('')),
    competition: optionalText(200, 'Keep the competition name under 200 characters.'),
    academic_year: z
      .string()
      .trim()
      .refine((value) => !value || /^\d{4}-\d{2}$/.test(value), 'Use the form YYYY-YY, for example 2026-27.')
      .optional()
      .or(z.literal('')),
    repository_url: optionalUrl,
    cad_url: optionalUrl,
    requirements_url: optionalUrl,
    public_project_id: z
      .string()
      .trim()
      .refine((value) => !value || /^\d+$/.test(value), 'Enter the numeric id of the public-site project.')
      .optional()
      .or(z.literal('')),
  })
  .refine((values) => !values.start_date || !values.target_date || values.target_date >= values.start_date, {
    message: 'The target date must be on or after the start date.',
    path: ['target_date'],
  })
export type ProjectInput = z.infer<typeof ProjectInput>

/** JSON body for POST/PATCH /projects (field names from services/projects.py). */
export interface ProjectPayload {
  name: string
  code?: string | null
  description: string | null
  status: ProjectStatus
  visibility: ProjectVisibility
  risk_level: RiskLevel
  lead_user_id: number | null
  faculty_advisor_user_id: number | null
  start_date: string | null
  target_date: string | null
  budget_amount: number | null
  competition: string | null
  academic_year: string | null
  repository_url: string | null
  cad_url: string | null
  requirements_url: string | null
  public_project_id: number | null
}

const blankToNull = (value: string | undefined) => (value && value.trim() ? value.trim() : null)

export function toProjectPayload(values: ProjectInput): ProjectPayload {
  const payload: ProjectPayload = {
    name: values.name.trim(),
    description: blankToNull(values.description),
    status: values.status,
    visibility: values.visibility,
    risk_level: values.risk_level,
    lead_user_id: values.lead_user_id ?? null,
    faculty_advisor_user_id: values.faculty_advisor_user_id ?? null,
    start_date: blankToNull(values.start_date),
    target_date: blankToNull(values.target_date),
    budget_amount: values.budget_amount && values.budget_amount.trim() ? Number(values.budget_amount) : null,
    competition: blankToNull(values.competition),
    academic_year: blankToNull(values.academic_year),
    repository_url: blankToNull(values.repository_url),
    cad_url: blankToNull(values.cad_url),
    requirements_url: blankToNull(values.requirements_url),
    public_project_id: values.public_project_id && values.public_project_id.trim() ? Number(values.public_project_id) : null,
  }
  const code = blankToNull(values.code)
  // A blank code is omitted: on create the server generates one, on edit the current code stays.
  if (code) payload.code = code.toUpperCase()
  return payload
}

export function projectToInput(project: Project): ProjectInput {
  return {
    name: project.name,
    code: project.code,
    description: project.description ?? '',
    status: (PROJECT_STATUSES as readonly string[]).includes(project.status) ? (project.status as ProjectStatus) : 'active',
    visibility: project.visibility === 'private' ? 'private' : 'chapter',
    risk_level: (RISK_LEVELS as readonly string[]).includes(project.risk_level ?? '') ? (project.risk_level as RiskLevel) : 'low',
    lead_user_id: project.lead?.id ?? null,
    faculty_advisor_user_id: project.faculty_advisor?.id ?? null,
    start_date: project.start_date ?? '',
    target_date: project.target_date ?? '',
    budget_amount: project.budget_amount === null || project.budget_amount === undefined ? '' : String(project.budget_amount),
    competition: project.competition ?? '',
    academic_year: project.academic_year ?? '',
    repository_url: project.repository_url ?? '',
    cad_url: project.cad_url ?? '',
    requirements_url: project.requirements_url ?? '',
    public_project_id: project.public_project_id === null || project.public_project_id === undefined ? '' : String(project.public_project_id),
  }
}

export const EMPTY_PROJECT_INPUT: ProjectInput = {
  name: '',
  code: '',
  description: '',
  status: 'active',
  visibility: 'chapter',
  risk_level: 'low',
  lead_user_id: null,
  faculty_advisor_user_id: null,
  start_date: '',
  target_date: '',
  budget_amount: '',
  competition: '',
  academic_year: '',
  repository_url: '',
  cad_url: '',
  requirements_url: '',
  public_project_id: '',
}

/* Milestone form ------------------------------------------------------------- */

export const MilestoneInput = z.object({
  name: z.string().trim().min(1, 'Give the milestone a name.').max(200, 'Keep the name under 200 characters.'),
  description: optionalText(5000),
  due_date: z.string().optional().or(z.literal('')),
  owner_user_id: z.number().nullable(),
  weight: z.number({ error: 'Enter a whole number of 1 or more.' }).int('Enter a whole number of 1 or more.').min(1, 'Weight must be at least 1.'),
  status: z.enum(MILESTONE_STATUSES),
})
export type MilestoneInput = z.infer<typeof MilestoneInput>

export interface MilestonePayload {
  name: string
  description: string | null
  due_date: string | null
  owner_user_id: number | null
  weight: number
  status: MilestoneStatus
}

export function toMilestonePayload(values: MilestoneInput): MilestonePayload {
  return {
    name: values.name.trim(),
    description: blankToNull(values.description),
    due_date: blankToNull(values.due_date),
    owner_user_id: values.owner_user_id ?? null,
    weight: values.weight,
    status: values.status,
  }
}

export function milestoneToInput(milestone: Milestone | null | undefined): MilestoneInput {
  const status = milestone?.status === 'missed' ? 'planned' : milestone?.status
  return {
    name: milestone?.name ?? '',
    description: milestone?.description ?? '',
    due_date: milestone?.due_date ?? '',
    owner_user_id: milestone?.owner?.id ?? null,
    weight: milestone?.weight ?? 1,
    status: (MILESTONE_STATUSES as readonly string[]).includes(status ?? '') ? (status as MilestoneStatus) : 'planned',
  }
}
