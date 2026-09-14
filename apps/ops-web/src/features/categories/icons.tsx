import {
  Battery,
  Bolt,
  Calendar,
  CalendarCheck,
  ClipboardList,
  Code,
  Cpu,
  Drill,
  FileText,
  FlaskConical,
  FolderKanban,
  Hammer,
  Package,
  Printer,
  Radio,
  Ruler,
  SearchCheck,
  Settings,
  ShieldAlert,
  ShoppingCart,
  Tag,
  TriangleAlert,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { createElement } from 'react'
import { HEX_COLOR_RE } from '@/api/contracts/categories'
import { cn } from '@/lib/cn'
import styles from './categories.module.css'

export interface CategoryIconOption {
  /** Value stored in `category.icon` (lucide kebab-case name). */
  name: string
  label: string
  /** Extra search terms, lower-case. */
  keywords: string
  Icon: LucideIcon
}

/** Curated lucide icons offered by the picker. `iconFor` falls back to Tag for anything else. */
export const CATEGORY_ICONS: readonly CategoryIconOption[] = [
  { name: 'tag', label: 'Tag', keywords: 'label general default', Icon: Tag },
  { name: 'wrench', label: 'Wrench', keywords: 'mechanical repair tool', Icon: Wrench },
  { name: 'zap', label: 'Lightning', keywords: 'electrical power energy', Icon: Zap },
  { name: 'code', label: 'Code', keywords: 'software programming firmware', Icon: Code },
  { name: 'cpu', label: 'Processor', keywords: 'embedded electronics chip controller', Icon: Cpu },
  { name: 'hammer', label: 'Hammer', keywords: 'fabrication build construction', Icon: Hammer },
  { name: 'search-check', label: 'Inspection', keywords: 'check review audit verify', Icon: SearchCheck },
  { name: 'shield-alert', label: 'Safety', keywords: 'hazard protection ppe', Icon: ShieldAlert },
  { name: 'calendar-check', label: 'Scheduled check', keywords: 'preventive maintenance routine', Icon: CalendarCheck },
  { name: 'alert-triangle', label: 'Warning', keywords: 'damage issue problem', Icon: TriangleAlert },
  { name: 'folder-kanban', label: 'Project board', keywords: 'project planning tasks', Icon: FolderKanban },
  { name: 'calendar', label: 'Calendar', keywords: 'event date outreach', Icon: Calendar },
  { name: 'shopping-cart', label: 'Shopping cart', keywords: 'procurement purchase order buy', Icon: ShoppingCart },
  { name: 'file-text', label: 'Document', keywords: 'documentation paper report', Icon: FileText },
  { name: 'clipboard-list', label: 'Checklist', keywords: 'procedure sop steps', Icon: ClipboardList },
  { name: 'settings', label: 'Settings', keywords: 'configuration gear tuning', Icon: Settings },
  { name: 'bolt', label: 'Bolt', keywords: 'fastener hardware nut', Icon: Bolt },
  { name: 'flask-conical', label: 'Flask', keywords: 'testing lab experiment', Icon: FlaskConical },
  { name: 'drill', label: 'Drill', keywords: 'machining shop power tool', Icon: Drill },
  { name: 'ruler', label: 'Ruler', keywords: 'measurement calibration dimension', Icon: Ruler },
  { name: 'printer', label: 'Printer', keywords: '3d printing additive', Icon: Printer },
  { name: 'battery', label: 'Battery', keywords: 'charging power cell', Icon: Battery },
  { name: 'radio', label: 'Radio', keywords: 'communications wireless telemetry', Icon: Radio },
  { name: 'package', label: 'Package', keywords: 'inventory shipping parts stock', Icon: Package },
]

export const ICONS: Readonly<Record<string, LucideIcon>> = Object.fromEntries(CATEGORY_ICONS.map((option) => [option.name, option.Icon]))

export function iconFor(name: string | null | undefined): LucideIcon {
  return (name && ICONS[name]) || Tag
}

export function iconLabel(name: string | null | undefined): string {
  if (!name) return 'Tag'
  return CATEGORY_ICONS.find((option) => option.name === name)?.label ?? name
}

/** Low-alpha version of a category colour for tile backgrounds. */
export function tint(hex: string, alpha = 0.14): string {
  const match = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!match) return 'var(--color-bg-subtle)'
  const value = parseInt(match[1], 16)
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}

export function safeColor(hex: string): string {
  return HEX_COLOR_RE.test(hex.trim()) ? hex.trim() : 'var(--color-text-muted)'
}

const TILE_ICON_SIZE = { sm: 13, md: 16, lg: 22 } as const

/** Coloured circular tile carrying the category icon. Decorative: the name sits next to it. */
export function CategoryIconTile({ color, icon, size = 'md', className }: { color: string; icon: string; size?: 'sm' | 'md' | 'lg'; className?: string }) {
  return (
    <span className={cn(styles.tile, size === 'sm' && styles.tile_sm, size === 'lg' && styles.tile_lg, className)} style={{ background: tint(color), color: safeColor(color) }} aria-hidden="true">
      {createElement(iconFor(icon), { size: TILE_ICON_SIZE[size] })}
    </span>
  )
}
