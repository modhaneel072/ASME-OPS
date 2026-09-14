import { X } from 'lucide-react'
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'
import { IconButton } from './Button'
import styles from './overlays.module.css'

export interface DialogProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl'
  /** When true, Escape and overlay clicks do not close (e.g. while submitting). */
  preventClose?: boolean
  initialFocusRef?: React.RefObject<HTMLElement | null>
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Dialog({ open, onClose, title, description, children, footer, size = 'md', preventClose = false, initialFocusRef }: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    const target = initialFocusRef?.current ?? panel?.querySelector<HTMLElement>('[data-autofocus]') ?? panel?.querySelector<HTMLElement>(FOCUSABLE) ?? panel
    target?.focus({ preventScroll: true })
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !preventClose) {
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key === 'Tab' && panel) {
        const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((n) => n.offsetParent !== null || n === document.activeElement)
        if (nodes.length === 0) {
          event.preventDefault()
          panel.focus()
          return
        }
        const first = nodes[0]
        const last = nodes[nodes.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      if (previous && document.contains(previous)) previous.focus({ preventScroll: true })
    }
  }, [open, onClose, preventClose, initialFocusRef])

  if (!open || typeof document === 'undefined') return null
  return createPortal(
    <div
      className={styles.dialogOverlay}
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !preventClose) onClose()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(styles.dialog, size !== 'md' && styles[`dialog_${size}`])}
      >
        <div className={styles.dialogHeader}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2 id={titleId} className={styles.dialogTitle}>
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className={styles.dialogDescription}>
                {description}
              </p>
            )}
          </div>
          <IconButton label="Close" onClick={onClose} disabled={preventClose} variant="ghost">
            <X size={18} />
          </IconButton>
        </div>
        {children && <div className={styles.dialogBody}>{children}</div>}
        {footer && <div className={styles.dialogFooter}>{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}
