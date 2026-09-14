import type { ReactNode } from 'react'
import styles from './shell.module.css'

export interface AuthLayoutProps {
  /** Page heading. When omitted the product name is the page's h1 (the sign-in page). */
  heading?: ReactNode
  /** Supporting text under the heading. */
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  busy?: boolean
}

/** The centred card shared by every signed-out account page. */
export function AuthLayout({ heading, description, children, footer, busy }: AuthLayoutProps) {
  const ProductName = heading ? 'p' : 'h1'
  return (
    <div className={styles.shell}>
      <main className={styles.centered}>
        <div className={styles.authCard} aria-busy={busy || undefined}>
          <div className={styles.authBrand}>
            <span className={styles.brandMark} aria-hidden="true">
              A
            </span>
            <div>
              <ProductName className={styles.authTitle}>ASME Ops</ProductName>
              <p className={styles.authSubtitle}>ASME at the University of Iowa</p>
            </div>
          </div>
          {heading && (
            <div className={styles.authIntro}>
              <h1 className={styles.authHeading}>{heading}</h1>
              {description && <div className={styles.authText}>{description}</div>}
            </div>
          )}
          {children}
          {footer && <div className={styles.authFooter}>{footer}</div>}
        </div>
      </main>
    </div>
  )
}
