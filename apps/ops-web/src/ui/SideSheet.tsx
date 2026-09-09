import { X } from 'lucide-react'
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { IconButton } from './Button'
import styles from './overlays.module.css'

export interface SideSheetProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  subtitle?: ReactNode
  children: ReactNode
  /** Sticky footer; typically Cancel + Create. */
  footer?: ReactNode
  footerStart?: ReactNode
  wide?: boolean
  headerActions?: ReactNode
  /** Called before closing on Escape/close button; return false to keep open. */
  onRequestClose?: () => boolean
  className?: string
}

/**
 * In-page right-side pane used for create/edit flows. It overlays the detail
 * region of a MasterDetailLayout (which is `position: relative`) so the list
 * stays visible and interactive. Below 900px it becomes a full-screen sheet.
 */
export function SideSheet({ open, onClose, title, subtitle, children, footer, footerStart, wide, headerActions, onRequestClose, className }: SideSheetProps) {
  const ref = useRef<HTMLElement>(null)
  const titleId = useId()

  const requestClose = () => {
    if (onRequestClose && onRequestClose() === false) return
    onClose()
  }

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const first = ref.current?.querySelector<HTMLElement>('[data-autofocus], input, textarea, select, button')
    first?.focus({ preventScroll: true })
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const target = event.target as HTMLElement | null
      if (target && target.closest('[role="menu"], [role="listbox"], [role="dialog"][aria-modal="true"]')) return
      if (ref.current?.contains(target)) {
        event.preventDefault()
        requestClose()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open) return null
  return (
    <aside ref={ref} className={cn(styles.sheet, wide && styles.sheet_wide, className)} role="dialog" aria-labelledby={titleId} aria-modal="false">
      <header className={styles.sheetHeader}>
        <div className={styles.sheetTitle}>
          <h2 id={titleId} className={styles.sheetTitle} style={{ fontSize: 'inherit', fontWeight: 'inherit' }}>
            {title}
          </h2>
          {subtitle && <p className={styles.sheetSubtitle}>{subtitle}</p>}
        </div>
        {headerActions}
        <IconButton label="Close panel" variant="ghost" onClick={requestClose}>
          <X size={18} />
        </IconButton>
      </header>
      <div className={cn(styles.sheetBody, 'scroll-y')}>{children}</div>
      {footer && (
        <footer className={styles.sheetFooter}>
          {footerStart && <div className={styles.sheetFooterStart}>{footerStart}</div>}
          {footer}
        </footer>
      )}
    </aside>
  )
}
