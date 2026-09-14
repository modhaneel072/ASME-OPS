import { Check } from 'lucide-react'
import { useCallback, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Popover, useAnchor, type Placement } from './Popover'
import styles from './overlays.module.css'

export type MenuItem =
  | {
      type?: 'item'
      key: string
      label: ReactNode
      icon?: ReactNode
      onSelect: () => void
      disabled?: boolean
      destructive?: boolean
      shortcut?: string
      checked?: boolean
      description?: string
    }
  | { type: 'separator'; key: string }
  | { type: 'label'; key: string; label: ReactNode }

export interface TriggerProps {
  ref: (node: HTMLElement | null) => void
  onClick: () => void
  onKeyDown: (event: KeyboardEvent) => void
  'aria-haspopup': 'menu'
  'aria-expanded': boolean
  'aria-controls': string | undefined
}

export interface DropdownMenuProps {
  items: MenuItem[]
  trigger: (props: TriggerProps, open: boolean) => ReactNode
  placement?: Placement
  align?: 'start' | 'end'
  minWidth?: number
  label?: string
  onOpenChange?: (open: boolean) => void
}

function isSelectable(item: MenuItem): item is Extract<MenuItem, { onSelect: () => void }> {
  return (item.type ?? 'item') === 'item' && !(item as { disabled?: boolean }).disabled
}

export function DropdownMenu({ items, trigger, placement, align = 'start', minWidth = 200, label, onOpenChange }: DropdownMenuProps) {
  const [open, setOpenState] = useState(false)
  const { anchor, ref } = useAnchor<HTMLElement>()
  const listRef = useRef<HTMLDivElement>(null)
  const id = useId()

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next)
      onOpenChange?.(next)
    },
    [onOpenChange],
  )

  const focusItem = (index: number) => {
    const nodes = listRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')
    if (!nodes || nodes.length === 0) return
    const clamped = (index + nodes.length) % nodes.length
    nodes[clamped]?.focus()
  }

  const currentIndex = () => {
    const nodes = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') ?? [])
    return nodes.indexOf(document.activeElement as HTMLElement)
  }

  const onMenuKeyDown = (event: KeyboardEvent) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        focusItem(currentIndex() + 1)
        break
      case 'ArrowUp':
        event.preventDefault()
        focusItem(currentIndex() - 1)
        break
      case 'Home':
        event.preventDefault()
        focusItem(0)
        break
      case 'End':
        event.preventDefault()
        focusItem(-1)
        break
      case 'Tab':
        setOpen(false)
        break
      default:
        break
    }
  }

  const triggerProps: TriggerProps = {
    ref,
    onClick: () => setOpen(!open),
    onKeyDown: (event) => {
      if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        setOpen(true)
      }
    },
    'aria-haspopup': 'menu',
    'aria-expanded': open,
    'aria-controls': open ? id : undefined,
  }

  return (
    <>
      {trigger(triggerProps, open)}
      <Popover
        open={open}
        onOpenChange={setOpen}
        anchor={anchor}
        placement={placement ?? (align === 'end' ? 'bottom-end' : 'bottom-start')}
        role="menu"
        id={id}
        className={styles.menu}
        label={label}
      >
        <div ref={listRef} role="none" style={{ minWidth }} onKeyDown={onMenuKeyDown}>
          {items.map((item) => {
            if (item.type === 'separator') return <div key={item.key} role="separator" className={styles.menuSeparator} />
            if (item.type === 'label')
              return (
                <div key={item.key} role="presentation" className={styles.menuLabel}>
                  {item.label}
                </div>
              )
            const selectable = isSelectable(item)
            return (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                className={styles.menuItem}
                aria-disabled={item.disabled ? 'true' : undefined}
                data-destructive={item.destructive ? 'true' : undefined}
                tabIndex={-1}
                onClick={() => {
                  if (!selectable) return
                  setOpen(false)
                  item.onSelect()
                }}
              >
                {item.checked !== undefined ? (
                  <span className={styles.menuCheck} aria-hidden="true">
                    {item.checked ? <Check size={16} /> : null}
                  </span>
                ) : item.icon ? (
                  <span className={styles.menuItemIcon} aria-hidden="true">
                    {item.icon}
                  </span>
                ) : null}
                <span className={cn(styles.menuItemLabel)}>
                  <span>{item.label}</span>
                  {item.description && <span style={{ display: 'block', fontSize: 'var(--text-caption)', color: 'var(--color-text-muted)' }}>{item.description}</span>}
                </span>
                {item.shortcut && <kbd className={styles.menuItemShortcut}>{item.shortcut}</kbd>}
              </button>
            )
          })}
        </div>
      </Popover>
    </>
  )
}
