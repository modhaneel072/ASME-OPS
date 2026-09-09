import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'
import styles from './overlays.module.css'

export type Placement = 'bottom-start' | 'bottom-end' | 'bottom' | 'top-start' | 'top-end' | 'right-start'

export interface PopoverProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  anchor: HTMLElement | null
  children: ReactNode
  placement?: Placement
  offset?: number
  matchWidth?: boolean
  className?: string
  role?: string
  id?: string
  labelledBy?: string
  label?: string
  /** Move focus into the popover when it opens (menus do; filter popovers do). */
  focusOnOpen?: boolean
  /** Return focus to the anchor when closing. */
  returnFocus?: boolean
  closeOnOutsideClick?: boolean
}

const MARGIN = 8

function computePosition(anchor: DOMRect, panel: DOMRect, placement: Placement, offset: number) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  let top: number
  let left: number
  let origin = 'top left'
  const wantsTop = placement.startsWith('top')
  const spaceBelow = vh - anchor.bottom - MARGIN
  const spaceAbove = anchor.top - MARGIN
  const showAbove = placement === 'right-start' ? false : wantsTop ? spaceAbove >= panel.height || spaceAbove > spaceBelow : spaceBelow < panel.height && spaceAbove > spaceBelow

  if (placement === 'right-start') {
    top = anchor.top
    left = anchor.right + offset
    origin = 'top left'
  } else if (showAbove) {
    top = anchor.top - panel.height - offset
    origin = 'bottom left'
  } else {
    top = anchor.bottom + offset
  }
  if (placement === 'bottom-end' || placement === 'top-end') {
    left = anchor.right - panel.width
    origin = showAbove ? 'bottom right' : 'top right'
  } else if (placement === 'bottom') {
    left = anchor.left + anchor.width / 2 - panel.width / 2
    origin = showAbove ? 'bottom center' : 'top center'
  } else if (placement !== 'right-start') {
    left = anchor.left
  }
  left = Math.max(MARGIN, Math.min(left!, vw - panel.width - MARGIN))
  top = Math.max(MARGIN, Math.min(top, vh - panel.height - MARGIN))
  return { top, left, origin }
}

export function Popover({
  open,
  onOpenChange,
  anchor,
  children,
  placement = 'bottom-start',
  offset = 6,
  matchWidth = false,
  className,
  role = 'dialog',
  id,
  labelledBy,
  label,
  focusOnOpen = true,
  returnFocus = true,
  closeOnOutsideClick = true,
}: PopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [style, setStyle] = useState<CSSProperties>({ visibility: 'hidden' })

  const reposition = useCallback(() => {
    const panel = panelRef.current
    if (!panel || !anchor) return
    const anchorRect = anchor.getBoundingClientRect()
    if (matchWidth) panel.style.width = `${anchorRect.width}px`
    const panelRect = panel.getBoundingClientRect()
    const { top, left, origin } = computePosition(anchorRect, panelRect, placement, offset)
    setStyle({ top, left, visibility: 'visible', ['--popover-origin' as string]: origin } as CSSProperties)
  }, [anchor, matchWidth, offset, placement])

  useLayoutEffect(() => {
    if (!open) return
    reposition()
    const handle = () => reposition()
    window.addEventListener('resize', handle)
    window.addEventListener('scroll', handle, true)
    return () => {
      window.removeEventListener('resize', handle)
      window.removeEventListener('scroll', handle, true)
    }
  }, [open, reposition, children])

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    if (focusOnOpen) {
      const panel = panelRef.current
      const first = panel?.querySelector<HTMLElement>('[data-autofocus], input, button, [tabindex="0"], [role="menuitem"], [role="option"]')
      ;(first ?? panel)?.focus({ preventScroll: true })
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onOpenChange(false)
      }
    }
    const onPointer = (event: PointerEvent) => {
      if (!closeOnOutsideClick) return
      const target = event.target as Node
      if (panelRef.current?.contains(target) || anchor?.contains(target)) return
      onOpenChange(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer, true)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer, true)
      if (returnFocus && previous && document.contains(previous)) previous.focus({ preventScroll: true })
    }
  }, [open, anchor, onOpenChange, focusOnOpen, returnFocus, closeOnOutsideClick])

  if (!open || typeof document === 'undefined') return null
  return createPortal(
    <div ref={panelRef} id={id} role={role} aria-labelledby={labelledBy} aria-label={label} tabIndex={-1} className={cn(styles.popover, className)} style={style}>
      {children}
    </div>,
    document.body,
  )
}

/** Small helper so components can hold the anchor element in state. */
export function useAnchor<T extends HTMLElement = HTMLElement>() {
  const [anchor, setAnchor] = useState<T | null>(null)
  const ref = useCallback((node: T | null) => setAnchor(node), [])
  return { anchor, ref }
}
