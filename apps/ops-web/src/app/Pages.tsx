import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState, LinkButton, PageHeader } from '@/ui'
import styles from './shell.module.css'

export function NotFoundPage() {
  return (
    <div className={styles.pageScroll}>
      <div className={styles.pageBody}>
        <EmptyState illustration="search" title="Page not found" description="The link may be out of date or the record may have been removed." action={<LinkButton to="/work-orders">Go to Work Orders</LinkButton>} />
      </div>
    </div>
  )
}

/**
 * Navigation target for modules that ship in a later stage. It is a page, not a
 * control: nothing on it pretends to work. The stage number tells the reader
 * where the module sits in the build plan.
 */
export function ComingSoon({ title, stage, description }: { title: string; stage: number; description: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className={styles.pageScroll}>
        <div className={styles.pageBody}>
          <EmptyState
            illustration="folder"
            title={`${title} arrives in Stage ${stage}`}
            description={
              <>
                {description} Progress is tracked in <code>docs/implementation-status.md</code>.
              </>
            }
            action={
              <Link to="/work-orders" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <ArrowLeft size={14} aria-hidden="true" /> Back to Work Orders
              </Link>
            }
          />
        </div>
      </div>
    </>
  )
}
