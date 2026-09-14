import {
  Activity,
  BarChart3,
  Bell,
  Boxes,
  CalendarDays,
  ClipboardList,
  Cpu,
  FolderKanban,
  Gauge,
  HandCoins,
  Inbox,
  Layers,
  Library,
  MapPin,
  MessageSquare,
  Package,
  Rocket,
  Settings2,
  ShoppingCart,
  Tag,
  Truck,
  Users,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  key: string
  label: string
  to: string
  icon: LucideIcon
  /** Stage in which the module ships; undefined means built. Shown as a tag. */
  stage?: number
  children?: Array<{ key: string; label: string; to: string; stage?: number }>
  /** Permission keys; the item is hidden when none is held. */
  permissions?: string[]
}

export interface NavGroup {
  key: string
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'setup',
    label: 'Setup',
    items: [{ key: 'setup', label: 'Setup Center', to: '/setup', icon: Rocket }],
  },
  {
    key: 'work',
    label: 'Work',
    items: [
      { key: 'projects', label: 'Projects', to: '/projects', icon: FolderKanban, permissions: ['project.read'] },
      { key: 'work-orders', label: 'Work Orders', to: '/work-orders', icon: ClipboardList, permissions: ['work_order.read_all', 'work_order.read_assigned', 'work_order.create'] },
      { key: 'requests', label: 'Requests', to: '/requests', icon: Inbox, stage: 3 },
      { key: 'messages', label: 'Messages', to: '/messages', icon: MessageSquare, stage: 3 },
      { key: 'events', label: 'Events', to: '/events', icon: CalendarDays, stage: 3 },
    ],
  },
  {
    key: 'optimize',
    label: 'Optimize',
    items: [
      {
        key: 'reporting',
        label: 'Reporting',
        to: '/reporting/operations',
        icon: BarChart3,
        permissions: ['report.view'],
        children: [
          { key: 'operations', label: 'Operations', to: '/reporting/operations' },
          { key: 'project-health', label: 'Project Health', to: '/reporting/project-health', stage: 7 },
          { key: 'asset-health', label: 'Asset Health', to: '/reporting/asset-health', stage: 7 },
          { key: 'details', label: 'Reporting Details', to: '/reporting/details', stage: 7 },
          { key: 'activity', label: 'Recent Activity', to: '/reporting/activity', stage: 7 },
          { key: 'exports', label: 'Export Data', to: '/reporting/exports', stage: 7 },
          { key: 'dashboards', label: 'Dashboards', to: '/reporting/dashboards', stage: 7 },
        ],
      },
      { key: 'automations', label: 'Automations', to: '/automations', icon: Zap, stage: 6 },
      { key: 'meters', label: 'Meters', to: '/meters', icon: Gauge, stage: 6 },
    ],
  },
  {
    key: 'manage',
    label: 'Manage',
    items: [
      { key: 'assets', label: 'Assets', to: '/assets', icon: Cpu, permissions: ['asset.read'] },
      { key: 'parts', label: 'Parts Inventory', to: '/parts', icon: Package, stage: 4 },
      { key: 'purchase-requests', label: 'Purchase Requests', to: '/purchase-requests', icon: ShoppingCart, stage: 4 },
      { key: 'maintenance-plans', label: 'Maintenance Plans', to: '/maintenance-plans', icon: Wrench, stage: 5 },
      {
        key: 'library',
        label: 'Library',
        to: '/library/work-order-templates',
        icon: Library,
        children: [
          { key: 'templates', label: 'Work Order Templates', to: '/library/work-order-templates', stage: 5 },
          { key: 'procedures', label: 'Procedures', to: '/library/procedures', stage: 5 },
          { key: 'documents', label: 'Documents', to: '/library/documents', stage: 5 },
        ],
      },
      { key: 'categories', label: 'Categories', to: '/categories', icon: Tag, permissions: ['category.read'] },
      { key: 'locations', label: 'Locations', to: '/locations', icon: MapPin, permissions: ['location.read'] },
      { key: 'teams-users', label: 'Teams / Users', to: '/teams-users', icon: Users, permissions: ['team.read', 'user.read'] },
      { key: 'vendors', label: 'Vendors', to: '/vendors', icon: Truck, permissions: ['vendor.read'] },
      { key: 'sponsors', label: 'Sponsors', to: '/sponsors', icon: HandCoins, stage: 8 },
    ],
  },
]

export const FOOTER_ICONS = { notifications: Bell, settings: Settings2, activity: Activity, layers: Layers, boxes: Boxes }
