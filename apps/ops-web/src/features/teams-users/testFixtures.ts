/** Shared fixtures for the Teams / Users tests; shapes follow the serializers in asme/ops/serializers/{teams,users}.py. */

export const ROUTE_PATHS = ['/teams-users', '/teams-users/:tab', '/teams-users/:tab/:itemId']

export const ADA = { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null }
export const LEE = { id: 2, name: 'Lee Lead', email: 'lee@uiowa.edu', avatar_url: null }
export const MO = { id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', avatar_url: null }

export const ROVER = { id: 'proj-1', name: 'Crater Cruncher Rover', code: 'CCR', visibility: 'chapter' }

export const TEAM_A = {
  id: 'team-a',
  name: 'Robotic Arm',
  description: 'Arm subsystem',
  parent_team_id: null,
  project: ROVER,
  leads: [LEE],
  member_count: 2,
  is_active: true,
  created_at: '2026-09-01T12:00:00Z',
  updated_at: '2026-09-01T12:00:00Z',
}

export const TEAM_B = {
  id: 'team-b',
  name: 'Wheels and Mobility',
  description: null,
  parent_team_id: null,
  project: null,
  leads: [],
  member_count: 0,
  is_active: true,
  created_at: '2026-09-02T12:00:00Z',
  updated_at: '2026-09-02T12:00:00Z',
}

export const TEAM_A_DETAIL = {
  ...TEAM_A,
  members: [
    { user: LEE, is_lead: true, joined_at: '2026-09-01T12:00:00Z' },
    { user: MO, is_lead: false, joined_at: '2026-09-01T12:00:00Z' },
  ],
}

export const TEAM_B_DETAIL = { ...TEAM_B, members: [] }

export const ROLE_ADMIN = { id: 'r-1', name: 'Chapter Administrator', system_key: 'chapter_admin', is_custom: false }
export const ROLE_LEAD = { id: 'r-4', name: 'Team Lead', system_key: 'team_lead', is_custom: false }
export const ROLE_MEMBER = { id: 'r-5', name: 'Full Member', system_key: 'full_member', is_custom: false }

export const MEMBER_ADA = { id: 'm-1', user: ADA, role: ROLE_ADMIN, status: 'active', title: 'President', teams: [], joined_at: '2026-08-20T00:00:00Z', last_login_at: '2026-09-08T15:00:00Z' }
export const MEMBER_LEE = { id: 'm-2', user: LEE, role: ROLE_LEAD, status: 'active', title: null, teams: [{ id: 'team-a', name: 'Robotic Arm' }], joined_at: '2026-08-21T00:00:00Z', last_login_at: null }
export const MEMBER_MO = { id: 'm-3', user: MO, role: ROLE_MEMBER, status: 'invited', title: null, teams: [{ id: 'team-a', name: 'Robotic Arm' }], joined_at: '2026-08-22T00:00:00Z', last_login_at: null }

export const ROLES = [
  {
    ...ROLE_ADMIN,
    description: 'All chapter settings, users, data, reporting and audit.',
    member_count: 1,
    grants: [
      { key: 'chapter.settings.manage', scope: 'chapter' },
      { key: 'team.manage', scope: 'chapter' },
      { key: 'team.read', scope: 'chapter' },
      { key: 'user.manage', scope: 'chapter' },
      { key: 'work_order.edit', scope: 'chapter' },
      { key: 'request.submit', scope: 'chapter' },
    ],
  },
  {
    ...ROLE_LEAD,
    description: 'Creates, assigns and manages work for own team.',
    member_count: 1,
    grants: [
      { key: 'team.manage', scope: 'team' },
      { key: 'team.read', scope: 'chapter' },
      { key: 'work_order.edit', scope: 'team' },
    ],
  },
  {
    ...ROLE_MEMBER,
    description: 'Executes work.',
    member_count: 3,
    grants: [
      { key: 'team.read', scope: 'chapter' },
      { key: 'work_order.edit', scope: 'own' },
      { key: 'request.submit', scope: 'chapter' },
    ],
  },
]

export function listOf<T>(items: T[]) {
  return { items, next_cursor: null, total: items.length }
}
