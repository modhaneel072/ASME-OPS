import { useParams } from 'react-router-dom'
import { ComingSoon } from '@/app/Pages'
import { OperationsDashboard } from './OperationsDashboard'

/** Reports that ship in a later stage, keyed by the `:report` route segment. */
const PLANNED_REPORTS: Record<string, { title: string; description: string }> = {
  'project-health': { title: 'Project Health', description: 'Milestone progress, overdue work and budget burn for every chapter project.' },
  'asset-health': { title: 'Asset Health', description: 'Downtime, failure history and maintenance cost for each asset.' },
  details: { title: 'Reporting Details', description: 'Drill from any Operations metric down to the individual work orders behind it.' },
  activity: { title: 'Recent Activity', description: 'A chapter-wide feed of who changed what, and when.' },
  exports: { title: 'Export Data', description: 'Download work orders, assets and time logs as CSV for advisors and sponsors.' },
  dashboards: { title: 'Dashboards', description: 'Pin the cards your team cares about into shared dashboards.' },
  builder: { title: 'Report Builder', description: 'Compose custom reports from any chapter data.' },
}

const PLANNED_STAGE = 7

function titleFromKey(key: string): string {
  return key
    .split(/[-_]+/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * `/reporting/:report` and `/reporting/dashboards/:dashboardId`. Only the
 * Operations dashboard exists in this stage; every other key is navigation to
 * a planned report and renders the ComingSoon page.
 */
export default function ReportingPage() {
  const { report, dashboardId } = useParams<{ report?: string; dashboardId?: string }>()
  if (dashboardId) {
    return <ComingSoon title={PLANNED_REPORTS.dashboards.title} stage={PLANNED_STAGE} description={PLANNED_REPORTS.dashboards.description} />
  }
  if (report === 'operations') return <OperationsDashboard />
  const planned = report ? PLANNED_REPORTS[report] : undefined
  return (
    <ComingSoon
      title={planned?.title ?? titleFromKey(report ?? 'reporting')}
      stage={PLANNED_STAGE}
      description={planned?.description ?? 'This report is planned for a later stage of ASME Ops.'}
    />
  )
}
