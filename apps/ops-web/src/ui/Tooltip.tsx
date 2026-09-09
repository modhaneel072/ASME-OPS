import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import styles from './overlays.module.css'

interface TooltipProps {
  content: ReactNode
  children: ReactNode
  side?: 'top' | 'bottom' | 'right'
  delayMs?: number
}

/**
 * Visual tooltip for controls that already carry an accessible name (icon
 * buttons use aria-label). The wrapper has no box of its own (display:
 * contents) so it never disturbs flex or grid layouts; the anchor rectangle is
 * read from the hovered/focused element itself.
 */
export function Tooltip({ content, children, side = 'top', delayMs = 350 }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 })
  const timer = useRef<number>(0)
  const id = useId()

  const show = (target: EventTarget | null) => {
    const element = target instanceof HTMLElement ? target : null
    if (!element) return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      const rect = element.getBoundingClientRect()
      const gap = 6
      if (side === 'right') setPos({ top: rect.top + rect.height / 2, left: rect.right + gap })
      else if (side === 'bottom') setPos({ top: rect.bottom + gap, left: rect.left + rect.width / 2 })
      else setPos({ top: rect.top - gap, left: rect.left + rect.width / 2 })
      setOpen(true)
    }, delayMs)
  }
  const hide = () => {
    window.clearTimeout(timer.current)
    setOpen(false)
  }

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const transform = side === 'right' ? 'translateY(-50%)' : side === 'bottom' ? 'translateX(-50%)' : 'translate(-50%, -100%)'

  return (
    <span style={{ display: 'contents' }} onMouseEnter={(event) => show(event.target)} onMouseLeave={hide} onFocusCapture={(event) => show(event.target)} onBlurCapture={hide}>
      {children}
      {open &&
        typeof document !== 'undefined' &&
        createPortal(
          <div id={id} role="tooltip" className={styles.tooltip} style={{ top: pos.top, left: pos.left, transform }}>
            {content}
          </div>,
          document.body,
        )}
    </span>
  )
}
