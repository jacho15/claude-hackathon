import { useEffect, useMemo, useState } from 'react'

const STATUS_LABELS = {
  occupied:         'Occupied',
  clinically_clear: 'Clinically clear',
  cleaning:         'Cleaning',
  ready:            'Ready',
  reserved:         'Reserved',
}

const WARD_LABELS = {
  cardiac: 'Cardiac',
  general: 'General',
}

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

function CountdownBar({ etaIso, totalMs = 12_000, now }) {
  if (!etaIso) return null
  const eta = new Date(etaIso).getTime()
  if (!Number.isFinite(eta)) return null
  const remainingMs = Math.max(0, eta - now)
  const elapsed = Math.max(0, Math.min(1, 1 - remainingMs / totalMs))
  const remainingSec = Math.ceil(remainingMs / 1000)
  return (
    <div className="bb-countdown">
      <div className="bb-countdown-bar">
        <div className="bb-countdown-fill" style={{ width: `${elapsed * 100}%` }} />
      </div>
      <span className="bb-countdown-label">
        {remainingMs > 0 ? `${remainingSec}s left` : 'finishing…'}
      </span>
    </div>
  )
}

function BedCard({ bed, now, onSelect }) {
  const statusKey = bed.status || 'occupied'
  const statusClass = `bb-pill bb-pill--${statusKey}`
  const occupant = bed.patients
  const showCountdown = statusKey === 'cleaning' && !!bed.cleaning_eta

  const subtitle = (() => {
    if (occupant?.full_name) return occupant.full_name
    if (statusKey === 'reserved') return bed.reserved_for || 'Inbound transfer'
    if (statusKey === 'ready') return 'Ready for next patient'
    return '—'
  })()

  return (
    <button
      type="button"
      className="bb-card"
      onClick={() => onSelect?.(bed)}
      aria-label={`Room ${bed.room_number}, ${STATUS_LABELS[statusKey] || statusKey}`}
    >
      <div className="bb-card-top">
        <div className="bb-room">Room {bed.room_number}</div>
        <div className={`bb-ward bb-ward--${bed.ward || 'general'}`}>
          {WARD_LABELS[bed.ward] || bed.ward || '—'}
        </div>
      </div>
      <div className={statusClass}>{STATUS_LABELS[statusKey] || statusKey}</div>
      <div className="bb-occupant">{subtitle}</div>
      {showCountdown && (
        <CountdownBar etaIso={bed.cleaning_eta} now={now} />
      )}
    </button>
  )
}

export default function BedBoard({ beds = [], workflows = [], onSelectWorkflow }) {
  const now = useNow(1000)

  const sorted = useMemo(
    () => [...beds].sort((a, b) => String(a.room_number).localeCompare(String(b.room_number))),
    [beds]
  )

  const counts = useMemo(() => {
    const c = { occupied: 0, clinically_clear: 0, cleaning: 0, ready: 0, reserved: 0 }
    for (const b of beds) {
      if (b.status in c) c[b.status] += 1
    }
    return c
  }, [beds])

  // Map of patient_id -> latest in-flight workflow (so clicking the
  // bed of a patient currently being discharged opens the right drawer).
  const workflowByPatient = useMemo(() => {
    const m = new Map()
    const inFlight = ['initiated', 'summary_drafted', 'transport_booked', 'room_released']
    for (const w of workflows) {
      if (!w.patient_id) continue
      if (inFlight.includes(w.status) || !m.has(w.patient_id)) {
        m.set(w.patient_id, w)
      }
    }
    return m
  }, [workflows])

  function handleSelect(bed) {
    const pid = bed.occupant_patient_id
    const wf = pid ? workflowByPatient.get(pid) : null
    if (wf) onSelectWorkflow?.(wf)
  }

  return (
    <section className="bed-board">
      <header className="bed-board-header">
        <h2>Bed Board</h2>
        <div className="bed-board-counts">
          <span className="bb-count">{counts.occupied} occupied</span>
          <span className="bb-count">{counts.clinically_clear} clear</span>
          <span className="bb-count">{counts.cleaning} cleaning</span>
          <span className="bb-count">{counts.ready} ready</span>
          <span className="bb-count">{counts.reserved} reserved</span>
        </div>
      </header>

      {sorted.length === 0 ? (
        <div className="bed-board-empty">No bed inventory yet.</div>
      ) : (
        <div className="bed-board-grid">
          {sorted.map(bed => (
            <BedCard
              key={bed.room_number}
              bed={bed}
              now={now}
              onSelect={handleSelect}
            />
          ))}
        </div>
      )}
    </section>
  )
}
