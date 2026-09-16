import { BarChart3, BookOpen, Building2, ClipboardList, Cpu, FolderKanban, Inbox, MapPin, Package, Tag, Users, Wrench, Zap, type LucideIcon } from 'lucide-react'
import type { SetupTask } from '@/api/contracts/setup'

/** Tile colours map onto token pairs in setup.module.css (`tile_<tone>`). */
export type TileTone = 'primary' | 'success' | 'purple' | 'gold' | 'warning' | 'neutral'

export interface TaskMeta {
  icon: LucideIcon
  tone: TileTone
}

const FALLBACK_META: TaskMeta = { icon: ClipboardList, tone: 'neutral' }

const TASK_META: Record<string, TaskMeta> = {
  chapter_profile: { icon: Building2, tone: 'primary' },
  locations: { icon: MapPin, tone: 'success' },
  assets: { icon: Cpu, tone: 'purple' },
  teams_users: { icon: Users, tone: 'gold' },
  officer_guide: { icon: BookOpen, tone: 'neutral' },
  first_project: { icon: FolderKanban, tone: 'primary' },
  categories: { icon: Tag, tone: 'warning' },
  parts: { icon: Package, tone: 'neutral' },
  procedure: { icon: ClipboardList, tone: 'neutral' },
  maintenance_plan: { icon: Wrench, tone: 'neutral' },
  request_portal: { icon: Inbox, tone: 'neutral' },
  automation: { icon: Zap, tone: 'neutral' },
  dashboard: { icon: BarChart3, tone: 'neutral' },
}

export function taskMeta(key: string): TaskMeta {
  return TASK_META[key] ?? FALLBACK_META
}

export function formatEstimate(minutes: number): string {
  if (minutes >= 60) {
    const hours = Math.round((minutes / 60) * 10) / 10
    return `~${hours} h`
  }
  return `~${minutes} min`
}

function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return count === 1 ? singular : pluralForm
}

/** Human label for the live count behind a task check; null when there is nothing to show. */
export function countLabel(task: Pick<SetupTask, 'key' | 'count' | 'status'>): string | null {
  if (task.count === null || task.status === 'unavailable') return null
  const n = task.count
  switch (task.key) {
    case 'locations':
      return `${n} ${plural(n, 'location')} added`
    case 'assets':
      return `${n} ${plural(n, 'asset')} registered`
    case 'teams_users':
      return `${n} active ${plural(n, 'member')}`
    case 'first_project':
      return `${n} ${plural(n, 'project')}`
    case 'categories':
      return `${n} ${plural(n, 'category', 'categories')}`
    case 'parts':
      return `${n} active ${plural(n, 'part')}`
    default:
      return `${n} so far`
  }
}
