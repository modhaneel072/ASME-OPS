/** Fixtures shared by the Work Orders tests (shapes mirror asme/ops/serializers/work_orders.py). */
import type { WorkOrder, WorkOrderDetail } from '@/api/contracts/work-orders'
import type { MockHandler } from '@/test/render'

export const ROUTES = ['/work-orders', '/work-orders/new', '/work-orders/:workOrderId', '/work-orders/:workOrderId/edit']

/** Argument passed to a function-style `mockApi` handler. */
export interface HandlerInit {
  url: URL
  body: unknown
  method: string
}

export const ADA = { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null }
export const LEE = { id: 2, name: 'Lee Lead', email: 'lee@uiowa.edu', avatar_url: null }
export const MO = { id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', avatar_url: null }

export const ROVER = { id: 'proj-1', name: 'Crater Cruncher Rover', code: 'CCR' }
export const ARM_TEAM = { id: 'team-1', name: 'Robotic Arm' }

export function makeWorkOrder(overrides: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 'wo-1',
    number: 12,
    title: 'Replace wheel hub bearing',
    description: 'Front-left hub is grinding under load.',
    status: 'open',
    priority: 'high',
    work_type: 'reactive',
    project: ROVER,
    location: { id: 'loc-1', name: 'Robotics Lab' },
    asset: { id: 'asset-1', name: 'Mobility System', code: 'MOB-01', status: 'online' },
    team: ARM_TEAM,
    assignees: [LEE],
    assignee_teams: [],
    watchers: [],
    categories: [{ id: 'cat-1', name: 'Mechanical', color: '#0878d1' }],
    vendor: null,
    parent_id: null,
    parent_number: null,
    parent_completion_policy: 'manual',
    sub_work_orders: { total: 0, done: 0 },
    start_at: null,
    due_at: '2026-09-15T17:00:00Z',
    completed_at: null,
    canceled_at: null,
    estimated_minutes: 90,
    actual_minutes: 0,
    is_overdue: false,
    is_blocked: false,
    budget_code: null,
    completion_note: null,
    created_by: ADA,
    created_at: '2026-09-01T12:00:00Z',
    updated_at: '2026-09-02T12:00:00Z',
    ...overrides,
  }
}

export function makeDetail(overrides: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return {
    ...makeWorkOrder(),
    status_history: [{ id: 'h-1', from_status: null, to_status: 'open', changed_by: ADA, note: null, changed_at: '2026-09-01T12:00:00Z' }],
    time_entries: [],
    cost_entries: [],
    dependencies: { blocked_by: [], blocking: [] },
    children: [],
    related_assets: [],
    ...overrides,
  }
}

const emptyList = { items: [], next_cursor: null, total: 0 }

/** Reference-data endpoints the screen touches; keep them quiet unless a test cares. */
export function baseHandlers(): Record<string, MockHandler> {
  return {
    'GET /users': {
      items: [
        { id: 'm-1', user: ADA, role: { id: 'r-1', name: 'Chapter Administrator', system_key: 'chapter_admin' }, status: 'active', teams: [] },
        { id: 'm-2', user: LEE, role: { id: 'r-3', name: 'Project Lead', system_key: 'project_lead' }, status: 'active', teams: [] },
        { id: 'm-3', user: MO, role: { id: 'r-5', name: 'Full Member', system_key: 'full_member' }, status: 'active', teams: [] },
      ],
      next_cursor: null,
      total: 3,
    },
    'GET /teams': { items: [{ id: ARM_TEAM.id, name: ARM_TEAM.name, leads: [] }], next_cursor: null, total: 1 },
    'GET /projects': { items: [{ id: ROVER.id, name: ROVER.name, code: ROVER.code, status: 'active', visibility: 'chapter' }], next_cursor: null, total: 1 },
    'GET /locations': { items: [{ id: 'loc-1', name: 'Robotics Lab', description: null, parent_id: null, building: null, room: null, is_default: false, path: ['Robotics Lab'], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }], next_cursor: null, total: 1 },
    'GET /assets': emptyList,
    'GET /categories': { items: [{ id: 'cat-1', name: 'Mechanical', color: '#0878d1', icon: 'wrench' }, { id: 'cat-2', name: 'Safety', color: '#d84a4a', icon: 'shield' }], next_cursor: null, total: 2 },
    'GET /vendors': emptyList,
    'GET /saved-filters': { personal: [], shared: [] },
    'GET /work-orders/:id/comments': emptyList,
    'GET /work-orders/:id/attachments': emptyList,
  }
}
