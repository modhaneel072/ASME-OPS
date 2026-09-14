import { useCallback, useSyncExternalStore } from 'react'

function canMatch(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
}

/**
 * Subscribes to a CSS media query. Candidate for `src/lib` once a second
 * feature needs it (listed in the slice's shared change requests).
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!canMatch()) return () => {}
      const media = window.matchMedia(query)
      media.addEventListener?.('change', onChange)
      return () => media.removeEventListener?.('change', onChange)
    },
    [query],
  )
  const getSnapshot = useCallback(() => (canMatch() ? window.matchMedia(query).matches : false), [query])
  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}
