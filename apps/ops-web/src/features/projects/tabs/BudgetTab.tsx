import type { Project } from '@/api/contracts/projects'
import { useProjectHealth } from '@/api/queries/projects'
import { formatMoney } from '@/lib/dates'
import { Card, LinkButton, Stack } from '@/ui'
import { QueryState, workOrdersHref } from '../shared'
import { BudgetSummary } from './OverviewTab'
import styles from '../projects.module.css'

export function BudgetTab({ project }: { project: Project }) {
  const health = useProjectHealth(project.id)
  return (
    <QueryState isPending={health.isPending} isError={health.isError} error={health.error} onRetry={() => void health.refetch()} title="Budget could not be loaded">
      {health.data && (
        <Stack>
          <Card title="Budget vs spend">
            <BudgetSummary budget={health.data.budget} />
          </Card>
          <Card
            title="Breakdown"
            flush
            actions={
              <LinkButton size="sm" to={workOrdersHref(project.id)}>
                Open work orders
              </LinkButton>
            }
          >
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">Line</th>
                    <th scope="col" className={styles.numeric}>
                      Amount
                    </th>
                    <th scope="col">Source</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Budget</td>
                    <td className={styles.numeric}>{health.data.budget.amount === null ? 'Not set' : formatMoney(health.data.budget.amount)}</td>
                    <td className={styles.muted}>Project settings</td>
                  </tr>
                  <tr>
                    <td>Spent</td>
                    <td className={styles.numeric}>{formatMoney(health.data.budget.used)}</td>
                    <td className={styles.muted}>Cost entries on {health.data.work.total} work orders</td>
                  </tr>
                  <tr>
                    <td>Remaining</td>
                    <td className={styles.numeric} style={health.data.budget.remaining !== null && health.data.budget.remaining < 0 ? { color: 'var(--color-danger-text)', fontWeight: 600 } : undefined}>
                      {health.data.budget.remaining === null ? '—' : formatMoney(health.data.budget.remaining)}
                    </td>
                    <td className={styles.muted}>Budget minus spend</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>
          <p className={styles.helpText}>Spend is the sum of cost entries logged on this project&apos;s work orders. Log costs from a work order to see them here.</p>
        </Stack>
      )}
    </QueryState>
  )
}
