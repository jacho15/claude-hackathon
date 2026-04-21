import { useState } from 'react'
import { reserveBed } from '../lib/supabase'

const SCENARIOS = [
  {
    id: 'cardiac',
    label: 'ER chest-pain inbound',
    detail: 'Cardiac, urgent',
    payload: {
      ward: 'cardiac',
      urgency: 'urgent',
      reason: 'ER chest-pain — cardiac telemetry needed',
    },
  },
  {
    id: 'general',
    label: 'Triage admission',
    detail: 'General, routine',
    payload: {
      ward: 'general',
      urgency: 'routine',
      reason: 'Triage admission from ER',
    },
  },
]

export default function EmergencyTrigger() {
  const [busy, setBusy] = useState(null)
  const [last, setLast] = useState(null)
  const [error, setError] = useState(null)

  async function handleClick(scenario) {
    setError(null)
    setBusy(scenario.id)
    try {
      const res = await reserveBed(scenario.payload)
      setLast({
        scenarioId: scenario.id,
        requestId: res?.request_id,
        at: new Date().toLocaleTimeString(),
      })
    } catch (err) {
      setError(err?.message || 'failed to reserve bed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="emergency-trigger">
      <div className="et-title">
        <span className="et-dot" />
        Demo controls
      </div>
      <div className="et-buttons">
        {SCENARIOS.map(s => (
          <button
            key={s.id}
            type="button"
            className={`et-button et-button--${s.id}`}
            onClick={() => handleClick(s)}
            disabled={busy !== null}
          >
            <span className="et-button-label">{s.label}</span>
            <span className="et-button-detail">{s.detail}</span>
            {busy === s.id && <span className="et-spinner" />}
          </button>
        ))}
      </div>
      <div className="et-status">
        {error && <span className="et-error">{error}</span>}
        {!error && last && (
          <span className="et-ok">
            queued <code>{last.requestId?.slice(0, 8)}…</code> at {last.at}
          </span>
        )}
      </div>
    </section>
  )
}
