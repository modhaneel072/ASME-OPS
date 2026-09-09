import { createBrowserRouter, Navigate, type RouteObject } from 'react-router-dom'
import { AppShell } from './AppShell'
import { LoginPage } from './LoginPage'
import { NotFoundPage } from './Pages'
import { RequireSession } from './RequireSession'

type Loader = () => Promise<{ default: React.ComponentType }>

/** Lazily loads a feature module's default export as the route component. */
function feature(load: Loader): Pick<RouteObject, 'lazy'> {
  return {
    lazy: async () => {
      const mod = await load()
      return { Component: mod.default }
    },
  }
}

const setup = feature(() => import('@/features/setup'))
const projects = feature(() => import('@/features/projects'))
const workOrders = feature(() => import('@/features/work-orders'))
const requests = feature(() => import('@/features/requests'))
const messages = feature(() => import('@/features/messages'))
const events = feature(() => import('@/features/events'))
const reporting = feature(() => import('@/features/reporting'))
const automations = feature(() => import('@/features/automations'))
const meters = feature(() => import('@/features/meters'))
const assets = feature(() => import('@/features/assets'))
const parts = feature(() => import('@/features/parts'))
const purchaseRequests = feature(() => import('@/features/purchase-requests'))
const maintenancePlans = feature(() => import('@/features/maintenance-plans'))
const library = feature(() => import('@/features/library'))
const categories = feature(() => import('@/features/categories'))
const locations = feature(() => import('@/features/locations'))
const teamsUsers = feature(() => import('@/features/teams-users'))
const vendors = feature(() => import('@/features/vendors'))
const sponsors = feature(() => import('@/features/sponsors'))
const settings = feature(() => import('@/features/settings'))
const notifications = feature(() => import('@/features/notifications'))

export const routes: RouteObject[] = [
  { path: '/auth/login', element: <LoginPage /> },
  { path: '/auth/verify', element: <Navigate to="/auth/login" replace /> },
  { path: '/auth/forgot-password', element: <Navigate to="/auth/login" replace /> },
  {
    element: <RequireSession />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/work-orders" replace /> },
          { path: 'setup', ...setup },
          { path: 'projects', ...projects },
          { path: 'projects/:projectId', ...projects },
          { path: 'projects/:projectId/:tab', ...projects },
          { path: 'work-orders', ...workOrders },
          { path: 'work-orders/new', ...workOrders },
          { path: 'work-orders/:workOrderId', ...workOrders },
          { path: 'work-orders/:workOrderId/edit', ...workOrders },
          { path: 'requests', ...requests },
          { path: 'requests/new', ...requests },
          { path: 'requests/:requestId', ...requests },
          { path: 'request-portals/:portalSlug', ...requests },
          { path: 'messages', ...messages },
          { path: 'messages/:conversationId', ...messages },
          { path: 'messages/:conversationId/thread/:messageId', ...messages },
          { path: 'events', ...events },
          { path: 'events/:eventId', ...events },
          { path: 'reporting', element: <Navigate to="/reporting/operations" replace /> },
          { path: 'reporting/:report', ...reporting },
          { path: 'reporting/dashboards/:dashboardId', ...reporting },
          { path: 'automations', ...automations },
          { path: 'automations/new', ...automations },
          { path: 'automations/:automationId', ...automations },
          { path: 'meters', ...meters },
          { path: 'meters/:meterId', ...meters },
          { path: 'assets', ...assets },
          { path: 'assets/:assetId', ...assets },
          { path: 'parts', ...parts },
          { path: 'parts/:partId', ...parts },
          { path: 'purchase-requests', ...purchaseRequests },
          { path: 'purchase-requests/:purchaseRequestId', ...purchaseRequests },
          { path: 'maintenance-plans', ...maintenancePlans },
          { path: 'maintenance-plans/:planId', ...maintenancePlans },
          { path: 'library', element: <Navigate to="/library/work-order-templates" replace /> },
          { path: 'library/:section', ...library },
          { path: 'library/:section/:itemId', ...library },
          { path: 'categories', ...categories },
          { path: 'categories/:categoryId', ...categories },
          { path: 'locations', ...locations },
          { path: 'locations/:locationId', ...locations },
          { path: 'teams-users', ...teamsUsers },
          { path: 'teams-users/:tab', ...teamsUsers },
          { path: 'teams-users/:tab/:itemId', ...teamsUsers },
          { path: 'vendors', ...vendors },
          { path: 'vendors/:vendorId', ...vendors },
          { path: 'sponsors', ...sponsors },
          { path: 'notifications', ...notifications },
          { path: 'settings', element: <Navigate to="/settings/profile" replace /> },
          { path: 'settings/:section', ...settings },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]

export const router = createBrowserRouter(routes, { basename: '/app' })
