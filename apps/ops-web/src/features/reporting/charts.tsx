/**
 * Inline-SVG chart primitives for report cards. No chart library: every mark is
 * a plain <rect>/<line>/<text>, coloured only through design tokens. The SVGs
 * are decorative (aria-hidden) because ChartFrame supplies the accessible
 * summary and the table alternative; interactive content (links) lives outside
 * the frame in legends rendered by the caller.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import styles from './reporting.module.css'

export interface Series {
  key: string
  label: string
  color: string
}

/** Width of the host element, tracked with ResizeObserver; `fallback` until measured. */
function useMeasuredWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const node = ref.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0)
      if (next > 0) setWidth((current) => (current === next ? current : next))
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return { ref, width }
}

/** Smallest "round" axis maximum at or above `value` (1, 2, 4, 5, 6, 8, 10 × 10^n). */
export function niceMax(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const step = [1, 2, 4, 5, 6, 8, 10].find((candidate) => candidate >= normalized) ?? 10
  return step * magnitude
}

/* Grouped vertical bars ------------------------------------------------------ */

export interface GroupedBarsProps {
  categories: Array<{ key: string; label: string; title?: string }>
  series: Array<Series & { values: number[] }>
  height?: number
}

export function GroupedBars({ categories, series, height = 220 }: GroupedBarsProps) {
  const { ref, width } = useMeasuredWidth<HTMLDivElement>()
  const pad = { top: 8, right: 8, bottom: 26, left: 36 }
  const plotW = Math.max(0, width - pad.left - pad.right)
  const plotH = Math.max(0, height - pad.top - pad.bottom)
  const rawMax = Math.max(0, ...series.flatMap((s) => s.values))
  const max = niceMax(rawMax)
  const ticks = max >= 2 ? [0, max / 2, max] : [0, 1]
  const count = categories.length
  const groupW = count ? plotW / count : plotW
  const inner = Math.min(groupW * 0.2, 12)
  const gap = 2
  const barW = Math.max(1, (groupW - inner * 2 - gap * (series.length - 1)) / Math.max(series.length, 1))
  const labelEvery = Math.max(1, Math.ceil((count * 56) / Math.max(plotW, 1)))

  return (
    <div ref={ref} className={styles.chartHost}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} className={styles.chart} aria-hidden="true" focusable="false">
        {ticks.map((tick) => {
          const y = pad.top + plotH - (tick / max) * plotH
          return (
            <g key={tick}>
              <line x1={pad.left} x2={pad.left + plotW} y1={y} y2={y} className={styles.gridLine} />
              <text x={pad.left - 6} y={y} dy="0.32em" textAnchor="end" className={styles.axisText}>
                {tick}
              </text>
            </g>
          )
        })}
        {categories.map((category, index) => {
          const x0 = pad.left + index * groupW + inner
          return (
            <g key={category.key}>
              {series.map((s, j) => {
                const value = s.values[index] ?? 0
                const h = (value / max) * plotH
                return (
                  <rect key={s.key} x={x0 + j * (barW + gap)} y={pad.top + plotH - h} width={barW} height={h} rx={2} fill={s.color}>
                    <title>{`${category.title ?? category.label}: ${value} ${s.label.toLowerCase()}`}</title>
                  </rect>
                )
              })}
              {index % labelEvery === 0 && (
                <text x={pad.left + index * groupW + groupW / 2} y={height - 8} textAnchor="middle" className={styles.axisText}>
                  {category.label}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* Horizontal bar rows -------------------------------------------------------- */

export interface BarRow {
  key: string
  /** Visible label; may be a badge or plain text. */
  label: ReactNode
  /** Plain-text name used in the hover title. */
  title: string
  value: number
  color: string
}

export function BarRows({ rows, max }: { rows: BarRow[]; max?: number }) {
  const top = Math.max(max ?? 0, ...rows.map((row) => row.value), 1)
  return (
    <ul className={styles.barRows}>
      {rows.map((row) => (
        <li key={row.key} className={styles.barRow}>
          <span className={styles.barLabel}>{row.label}</span>
          <svg className={styles.barTrack} viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true" focusable="false">
            <rect x={0} y={0} width={100} height={10} className={styles.trackBg} />
            {row.value > 0 && (
              <rect x={0} y={0} width={(row.value / top) * 100} height={10} fill={row.color}>
                <title>{`${row.title}: ${row.value}`}</title>
              </rect>
            )}
          </svg>
          <span className={styles.barValue}>{row.value}</span>
        </li>
      ))}
    </ul>
  )
}

/* Single stacked bar --------------------------------------------------------- */

export interface Segment {
  key: string
  label: string
  value: number
  color: string
}

export function SegmentBar({ segments, height = 16 }: { segments: Segment[]; height?: number }) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  const visible = segments.filter((segment) => segment.value > 0)
  const gap = visible.length > 1 ? 0.4 : 0
  const usable = 100 - gap * (visible.length - 1)
  const placed = visible.reduce<Array<Segment & { x: number; width: number }>>((acc, segment) => {
    const previous = acc[acc.length - 1]
    const x = previous ? previous.x + previous.width + gap : 0
    acc.push({ ...segment, x, width: (segment.value / total) * usable })
    return acc
  }, [])
  return (
    <svg className={styles.segmentBar} viewBox="0 0 100 10" preserveAspectRatio="none" style={{ height }} aria-hidden="true" focusable="false">
      {total === 0 ? (
        <rect x={0} y={0} width={100} height={10} className={styles.trackBg} />
      ) : (
        placed.map((segment) => (
          <rect key={segment.key} x={segment.x} y={0} width={segment.width} height={10} fill={segment.color}>
            <title>{`${segment.label}: ${segment.value}`}</title>
          </rect>
        ))
      )}
    </svg>
  )
}

/* Legend --------------------------------------------------------------------- */

export interface LegendItem {
  key: string
  label: ReactNode
  color: string
  value?: ReactNode
  /** When set, the whole item is a drill-down link. */
  to?: string
}

export function Legend({ items, label }: { items: LegendItem[]; label?: string }) {
  return (
    <ul className={styles.legend} aria-label={label}>
      {items.map((item) => {
        const body = (
          <>
            <span className={styles.swatch} style={{ background: item.color }} aria-hidden="true" />
            <span>{item.label}</span>
            {item.value !== undefined && (
              <>
                {' '}
                <span className={styles.legendValue}>{item.value}</span>
              </>
            )}
          </>
        )
        return (
          <li key={item.key}>
            {item.to ? (
              <Link to={item.to} className={styles.legendLink}>
                {body}
              </Link>
            ) : (
              <span className={styles.legendItem}>{body}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
