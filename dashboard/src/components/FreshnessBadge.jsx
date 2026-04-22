import { useEffect, useState } from 'react'

/**
 * Phase 1.5 freshness pill.
 *
 * Renders nothing if `setAt` is null / undefined (we don't know when this
 * field was last touched, so we shouldn't claim anything about it).
 *
 * Colour bands match the README §6.5 spec:
 *   < 5  min  → fresh  (green)
 *   5–30 min  → stale  (amber)
 *   > 30 min  → cold   (red)
 *
 * The component re-renders itself every 30 s so badges age visibly during
 * the demo without the parent having to push new props.
 */
export default function FreshnessBadge({ setAt, prefix = '·', className = '' }) {
  const [, force] = useState(0)
  useEffect(() => {
    const id = setInterval(() => force(n => n + 1), 30_000)
    return () => clearInterval(id)
  }, [])

  if (!setAt) return null
  const ts = new Date(setAt).getTime()
  if (!Number.isFinite(ts)) return null

  const mins = Math.max(0, Math.floor((Date.now() - ts) / 60_000))
  const tone = mins < 5 ? 'fresh' : mins < 30 ? 'stale' : 'cold'
  const label = mins < 1 ? 'now' : `${mins} m`

  const title =
    tone === 'fresh' ? `Updated ${label} ago — within protocol`
    : tone === 'stale' ? `${label} since last update — check soon`
    : `${label} since last update — overdue`

  return (
    <span
      className={`freshness freshness--${tone} ${className}`}
      title={title}
      aria-label={title}
    >
      {prefix && <span className="freshness-prefix">{prefix}</span>}
      {label}
    </span>
  )
}
