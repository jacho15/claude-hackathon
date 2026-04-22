import { useEffect, useState } from 'react'
import { fetchDischargeSummaries } from '../lib/supabase'

const STAGE_ORDER = [
  'initiated',
  'summary_drafted',
  'transport_booked',
  'room_released',
  'completed',
]

const STAGE_LABELS = {
  initiated:        'Discharge initiated',
  summary_drafted:  'Summary drafted',
  transport_booked: 'Transport booked',
  room_released:    'Room released',
  completed:        'Completed',
  cancelled:        'Cancelled',
}

function StageTimeline({ status }) {
  const cancelled = status === 'cancelled'
  const currentIdx = cancelled ? STAGE_ORDER.length : STAGE_ORDER.indexOf(status)

  return (
    <ol className="dd-timeline">
      {STAGE_ORDER.map((stage, idx) => {
        const done = idx < currentIdx
        const active = idx === currentIdx
        const cls = [
          'dd-stage',
          done && 'dd-stage--done',
          active && 'dd-stage--active',
        ].filter(Boolean).join(' ')
        return (
          <li key={stage} className={cls}>
            <span className="dd-stage-dot" />
            <span className="dd-stage-label">{STAGE_LABELS[stage]}</span>
          </li>
        )
      })}
      {cancelled && (
        <li className="dd-stage dd-stage--cancelled">
          <span className="dd-stage-dot" />
          <span className="dd-stage-label">Cancelled</span>
        </li>
      )}
    </ol>
  )
}

export default function DischargeDrawer({ workflow, onClose }) {
  const open = !!workflow
  const [summaries, setSummaries] = useState([])
  const [activeLang, setActiveLang] = useState(null)
  const [loading, setLoading] = useState(false)

  // Reset summaries when the drawer switches to a different workflow
  // (otherwise the previous discharge's EN/ES rows briefly flash in).
  useEffect(() => {
    setSummaries([])
    setActiveLang(null)
  }, [workflow?.id])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)

    // Single fetch helper; reused by the initial pull AND the poll
    // so both paths go through the same state-update logic.
    function refresh() {
      return fetchDischargeSummaries(workflow.id)
        .then(rows => { if (!cancelled) setSummaries(rows) })
        .catch(() => { if (!cancelled) setSummaries([]) })
    }

    refresh().finally(() => { if (!cancelled) setLoading(false) })

    // Claude usually takes ~3-5s to draft the EN+ES rows. The
    // workflow row update arrives FIRST (status=summary_drafted)
    // because the agent flips status before the summary inserts
    // commit, so a one-shot subscription on the workflow row would
    // race the data. Poll for ~30s instead — long enough for slow
    // model responses, short enough to stop on its own.
    const id = setInterval(refresh, 1500)
    const stop = setTimeout(() => clearInterval(id), 30_000)

    return () => {
      cancelled = true
      clearInterval(id)
      clearTimeout(stop)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow?.id, open])

  // Auto-select the first language tab as soon as ANY summary lands,
  // regardless of which fetch fired (initial vs poll). The previous
  // version only set this in the initial-fetch handler, so when
  // Claude took >0ms to respond (it always does) activeLang stayed
  // null and the renderer fell through to the placeholder forever.
  useEffect(() => {
    if (!summaries.length) return
    if (activeLang && summaries.find(s => s.language === activeLang)) return
    setActiveLang(summaries[0].language)
  }, [summaries, activeLang])

  if (!open) return null

  const patientName = workflow.patients?.full_name || 'Patient'
  const room = workflow.patients?.room_number || '—'
  const status = workflow.status || 'initiated'
  const activeSummary = summaries.find(s => s.language === activeLang)

  return (
    <>
      <div className="dd-backdrop" onClick={onClose} />
      <aside className="dd-drawer" role="dialog" aria-label="Discharge workflow">
        <header className="dd-header">
          <div>
            <h2>Discharge workflow</h2>
            <div className="dd-subtitle">{patientName} · Room {room}</div>
          </div>
          <button type="button" className="dd-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <section className="dd-section">
          <h3>Workflow stage</h3>
          <StageTimeline status={status} />
        </section>

        <section className="dd-section">
          <div className="dd-summary-tabs">
            <h3>Discharge summary</h3>
            <div className="dd-tabs">
              {summaries.length === 0 && (
                <span className="dd-tab dd-tab--placeholder">
                  {loading ? 'loading…' : 'awaiting Claude'}
                </span>
              )}
              {summaries.map(s => (
                <button
                  key={s.language}
                  type="button"
                  className={`dd-tab ${activeLang === s.language ? 'dd-tab--active' : ''}`}
                  onClick={() => setActiveLang(s.language)}
                >
                  {s.language.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div className="dd-summary-body">
            {activeSummary
              ? <p>{activeSummary.content}</p>
              : <p className="dd-summary-placeholder">
                  Once Claude finishes drafting, the EN and translated
                  summaries will appear here.
                </p>
            }
          </div>
        </section>

        <footer className="dd-footer">
          <span>Workflow ID: <code>{workflow.id?.slice(0, 8)}…</code></span>
          <span>Started: {workflow.started_at ? new Date(workflow.started_at).toLocaleTimeString() : '—'}</span>
        </footer>
      </aside>
    </>
  )
}
