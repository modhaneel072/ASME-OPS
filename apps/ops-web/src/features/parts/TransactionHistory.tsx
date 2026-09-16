import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { formatQuantity, transactionTypeLabel } from '@/api/contracts/parts'
import { usePartTransactions } from '@/api/queries/parts'
import { formatDateTime } from '@/lib/dates'
import { Button, Card, EmptyState, InlineAlert, LoadMore, SkeletonRows } from '@/ui'
import { DeltaText } from './bits'
import styles from './parts.module.css'

/**
 * The part's ledger, newest first. Rows are never edited or deleted, so this is
 * the part's whole history: a correction appears as another row.
 */
export function TransactionHistory({ partId, unit }: { partId: string; unit: string }) {
  const history = usePartTransactions(partId)
  const rows = useMemo(() => (history.data?.pages ?? []).flatMap((page) => page.items), [history.data])
  const total = history.data?.pages[0]?.total

  return (
    <Card title={`History${total !== undefined ? ` (${total})` : ''}`} flush>
      {history.isPending ? (
        <SkeletonRows rows={4} />
      ) : history.isError ? (
        <div className={styles.padded}>
          <InlineAlert tone="danger" title="History could not be loaded" actions={<Button size="sm" onClick={() => void history.refetch()}>Retry</Button>}>
            {errorMessage(history.error)}
          </InlineAlert>
        </div>
      ) : rows.length === 0 ? (
        <EmptyState compact illustration="clipboard" title="No movements yet" description="Receipts, issues, transfers and counts all land here the moment they happen." />
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className="sr-only">Every recorded movement of this part, newest first</caption>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Movement</th>
                  <th scope="col" className={styles.numeric}>{`Change (${unit})`}</th>
                  <th scope="col" className={styles.numeric}>
                    On hand after
                  </th>
                  <th scope="col">Location</th>
                  <th scope="col">Reference</th>
                  <th scope="col">By</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} style={{ cursor: 'default' }}>
                    <td>
                      <time dateTime={row.created_at}>{formatDateTime(row.created_at)}</time>
                    </td>
                    <td>
                      {transactionTypeLabel(row.type)}
                      {row.note && <div className={styles.historyNote}>{row.note}</div>}
                    </td>
                    <td className={styles.numeric}>
                      <DeltaText value={row.on_hand_delta} />
                      {row.type === 'cycle_count' && row.counted_quantity !== null && row.counted_quantity !== undefined && (
                        <div className={styles.cellMuted}>counted {formatQuantity(row.counted_quantity)}</div>
                      )}
                    </td>
                    <td className={styles.numeric}>{formatQuantity(row.on_hand_after)}</td>
                    <td className={styles.cellMuted}>{row.location?.name ?? '—'}</td>
                    <td>
                      {row.work_order ? (
                        <Link to={`/work-orders/${row.work_order.id}`}>#{row.work_order.number}</Link>
                      ) : row.purchase_request ? (
                        <Link to={`/purchase-requests/${row.purchase_request.id}`}>{row.purchase_request.display_number}</Link>
                      ) : (
                        <span className={styles.cellMuted}>—</span>
                      )}
                    </td>
                    <td className={styles.cellMuted}>{row.created_by?.name ?? 'System'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <LoadMore loaded={rows.length} total={total} hasMore={Boolean(history.hasNextPage)} loading={history.isFetchingNextPage} onLoadMore={() => void history.fetchNextPage()} />
        </>
      )}
    </Card>
  )
}
