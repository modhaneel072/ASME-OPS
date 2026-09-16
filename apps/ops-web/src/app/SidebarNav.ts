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
  children?: Array<{ key: string; label: string; to: string }>
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
      { key: 'requests', label: 'Requests', to: '/requests', icon: Inbox },
      { key: 'messages', label: 'Messages', to: '/messages', icon: MessageSquare },
      { key: 'events', label: 'Events', to: '/events', icon: CalendarDays },
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
          { key: 'project-health', label: 'Project Health', to: '/reporting/project-health' },
          { key: 'asset-health', label: 'Asset Health', to: '/reporting/asset-health' },
          { key: 'details', label: 'Reporting Details', to: '/reporting/details' },
          { key: 'activity', label: 'Recent Activity', to: '/reporting/activity' },
          { key: 'exports', label: 'Export Data', to: '/reporting/exports' },
          { key: 'dashboards', label: 'Dashboards', to: '/reporting/dashboards' },
        ],
      },
      { key: 'automations', label: 'Automations', to: '/automations', icon: Zap },
      { key: 'meters', label: 'Meters', to: '/meters', icon: Gauge },
    ],
  },
  {
    key: 'manage',
    label: 'Manage',
    items: [
      { key: 'assets', label: 'Assets', to: '/assets', icon: Cpu, permissions: ['asset.read'] },
      { key: 'parts', label: 'Parts Inventory', to: '/parts', icon: Package, permissions: ['inventory.read'] },
      { key: 'purchase-requests', label: 'Purchase Requests', to: '/purchase-requests', icon: ShoppingCart, permissions: ['purchase.submit', 'purchase.review', 'purchase.advisor_review', 'inventory.manage'] },
      { key: 'maintenance-plans', label: 'Maintenance Plans', to: '/maintenance-plans', icon: Wrench },
      {
        key: 'library',
        label: 'Library',
        to: '/library/work-order-templates',
        icon: Library,
        children: [
          { key: 'templates', label: 'Work Order Templates', to: '/library/work-order-templates' },
          { key: 'procedures', label: 'Procedures', to: '/library/procedures' },
          { key: 'documents', label: 'Documents', to: '/library/documents' },
        ],
      },
      { key: 'categories', label: 'Categories', to: '/categories', icon: Tag, permissions: ['category.read'] },
      { key: 'locations', label: 'Locations', to: '/locations', icon: MapPin, permissions: ['location.read'] },
      { key: 'teams-users', label: 'Teams / Users', to: '/teams-users', icon: Users, permissions: ['team.read', 'user.read'] },
      { key: 'vendors', label: 'Vendors', to: '/vendors', icon: Truck, permissions: ['vendor.read'] },
      { key: 'sponsors', label: 'Sponsors', to: '/sponsors', icon: HandCoins },
    ],
  },
]

export const FOOTER_ICONS = { notifications: Bell, settings: Settings2, activity: Activity, layers: Layers, boxes: Boxes }
