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
 * Navigation target for a module that is not built yet. It is a page, not a
 * control: nothing on it pretends to work.
 */
export function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <>
      <PageHeader title={title} />
      <div className={styles.pageScroll}>
        <div className={styles.pageBody}>
          <EmptyState
            illustration="folder"
            title={`${title} is coming soon`}
            description={description}
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
