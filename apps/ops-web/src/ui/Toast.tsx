import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'
import styles from './overlays.module.css'

export type ToastTone = 'info' | 'success' | 'error'

export interface ToastInput {
  title: string
  description?: string
  tone?: ToastTone
  action?: { label: string; onClick: () => void }
  durationMs?: number
}

interface ToastItem extends ToastInput {
  id: number
}

interface ToastApi {
  push: (toast: ToastInput) => number
  dismiss: (id: number) => void
  success: (title: string, description?: string) => number
  error: (title: string, description?: string) => number
  info: (title: string, description?: string) => number
}

const ToastContext = createContext<ToastApi | null>(null)

const ICONS: Record<ToastTone, typeof Info> = { info: Info, success: CheckCircle2, error: AlertCircle }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const counter = useRef(0)
  const timers = useRef(new Map<number, number>())

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id))
    const timer = timers.current.get(id)
    if (timer) window.clearTimeout(timer)
    timers.current.delete(id)
  }, [])

  const push = useCallback(
    (toast: ToastInput) => {
      const id = ++counter.current
      const tone = toast.tone ?? 'info'
      setItems((current) => [...current.slice(-2), { ...toast, tone, id }])
      const duration = toast.durationMs ?? (tone === 'error' ? 8000 : 5000)
      if (duration > 0) {
        timers.current.set(
          id,
          window.setTimeout(() => dismiss(id), duration),
        )
      }
      return id
    },
    [dismiss],
  )

  useEffect(() => {
    const pending = timers.current
    return () => {
      pending.forEach((timer) => window.clearTimeout(timer))
    }
  }, [])

  const api = useMemo<ToastApi>(
    () => ({
      push,
      dismiss,
      success: (title, description) => push({ title, description, tone: 'success' }),
      error: (title, description) => push({ title, description, tone: 'error' }),
      info: (title, description) => push({ title, description, tone: 'info' }),
    }),
    [push, dismiss],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      {typeof document !== 'undefined' &&
        createPortal(
          <div className={styles.toastRegion} role="region" aria-label="Notifications">
            <div role="status" aria-live="polite" aria-atomic="false">
              {items.map((item) => {
                const Icon = ICONS[item.tone ?? 'info']
                return (
                  <div key={item.id} className={cn(styles.toast, styles[`toast_${item.tone ?? 'info'}`])}>
                    <Icon className={styles.toastIcon} aria-hidden="true" size={18} />
                    <div className={styles.toastBody}>
                      <p className={styles.toastTitle}>{item.title}</p>
                      {item.description && <p className={styles.toastDescription}>{item.description}</p>}
                      {item.action && (
                        <button
                          type="button"
                          className={styles.toastAction}
                          onClick={() => {
                            item.action?.onClick()
                            dismiss(item.id)
                          }}
                        >
                          {item.action.label}
                        </button>
                      )}
                    </div>
                    <button type="button" className={styles.toastClose} aria-label="Dismiss notification" onClick={() => dismiss(item.id)}>
                      <X size={14} aria-hidden="true" />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>,
          document.body,
        )}
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext)
  if (!api) throw new Error('useToast must be used inside ToastProvider')
  return api
}
