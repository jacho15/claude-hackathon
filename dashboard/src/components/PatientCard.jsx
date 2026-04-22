import { useEffect, useState } from 'react'
import FlagBadge from './FlagBadge'
import FreshnessBadge from './FreshnessBadge'
import { acknowledgeFlag, callDoctor, setManualField } from '../lib/supabase'

const ACVPU_OPTIONS = ['A', 'C', 'V', 'P', 'U']

const SPARK_COLOR = { critical: '#EF4444', watch: '#F59E0B', stable: '#22C55E' }

// Phase 2: discharge_status is written by the discharge agent and
// mirrored to patient_current_state.discharge_status. The values
// match the DischargeStatusUpdate.stage vocabulary.
const DISCHARGE_LABELS = {
  initiated:       'Discharge initiated',
  summary_drafted: 'Summary drafted',
  transport_booked:'Transport booked',
  room_released:   'Room released',
  completed:       'Discharged',
  cleared:         null,
}

function DischargeBadge({ status }) {
  if (!status) return null
  const label = DISCHARGE_LABELS[status]
  if (label === null || label === undefined) return null
  return (
    <span
      className={`discharge-badge discharge-badge--${status}`}
      title={`Discharge workflow: ${status}`}
    >
      {label}
    </span>
  )
}

function getAge(dob) {
  if (!dob) return '—'
  return Math.floor((Date.now() - new Date(dob)) / (365.25 * 24 * 3600 * 1000))
}

function VitalCell({ category, value, unit, hi, lo, setAt }) {
  const cls = hi ? 'vital--hi' : lo ? 'vital--lo' : ''
  return (
    <div className="vital-cell">
      <span className={`vital-number ${cls}`}>
        {value}
        {hi && <span className="vital-arrow">↑</span>}
        {lo && <span className="vital-arrow">↓</span>}
      </span>
      <span className="vital-sublabel">
        <span className="vital-category">{category}</span>
        {unit && <span className="vital-unit"> {unit}</span>}
      </span>
      {setAt && <FreshnessBadge setAt={setAt} prefix="" className="vital-freshness" />}
    </div>
  )
}

/**
 * Sparkline fed from real `vitals_readings` rows.
 *
 * We re-query on mount and whenever `lastUpdated` changes — that prop is the
 * `patient_current_state.last_updated` timestamp, which ticks every time the
 * Floor Aggregator writes new vitals. (We can't subscribe directly to
 * vitals_readings because it isn't in the supabase_realtime publication.)
 *
 * Falls back to a flag-keyed demo array if the table is empty, so brand-new
 * patients still render something instead of a flat line.
 */
function Sparkline({ patientId, lastUpdated, flag }) {
  const [rows, setRows] = useState(null)

  useEffect(() => {
    if (!patientId) return
    let cancelled = false
    fetchPatientTrend(patientId, 20)
      .then(r => { if (!cancelled) setRows(r) })
      .catch(() => { if (!cancelled) setRows([]) })
    return () => { cancelled = true }
  }, [patientId, lastUpdated])

  const hrSeries = (rows ?? [])
    .map(r => Number(r.hr))
    .filter(v => Number.isFinite(v))

  const haveReal = hrSeries.length >= 2
  const raw = haveReal ? hrSeries : (FALLBACK_TREND[flag] ?? [50, 50, 50, 50, 50, 50, 50, 50])

  const W = 100, H = 24, pad = 2
  const max = Math.max(...raw), min = Math.min(...raw), range = max - min || 1
  const pts = raw.map((v, i) => {
    const x = (i / (raw.length - 1)) * W
    const y = H - pad - ((v - min) / range) * (H - pad * 2)
    return `${x},${y}`
  }).join(' ')

  const label = haveReal
    ? `HR · last ${formatWindow(rows)}`
    : rows === null ? 'loading…' : 'no history yet'

  return (
    <div className="sparkline-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="sparkline-svg" preserveAspectRatio="none">
        <polyline
          points={pts}
          fill="none"
          stroke={SPARK_COLOR[flag] ?? '#94A3B8'}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={haveReal ? 0.9 : 0.35}
          strokeDasharray={haveReal ? undefined : '2 2'}
        />
      </svg>
      <span className="sparkline-label">{label}</span>
    </div>
  )
}

function ManualControls({ patient }) {
  const {
    patient_id,
    consciousness,
    on_oxygen,
    o2_flow_rate,
    bp_sys,
    bp_dia,
    temp_c,
    acvpu_set_at,
    o2_set_at,
  } = patient

  const [acvpu, setAcvpu]   = useState(consciousness ?? 'A')
  const [o2, setO2]         = useState(!!on_oxygen)
  const [flow, setFlow]     = useState(o2_flow_rate ?? 2)
  const [bpS, setBpS]       = useState(bp_sys ?? '')
  const [bpD, setBpD]       = useState(bp_dia ?? '')
  const [t, setT]           = useState(temp_c ?? '')
  const [busy, setBusy]     = useState(false)
  const [err, setErr]       = useState(null)

  // Re-sync from the authoritative server snapshot whenever it lands
  // (Supabase Realtime push). We only overwrite fields the user isn't
  // actively editing — naive replace is fine for ACVPU/O₂ but BP/Temp
  // live behind a disclosure, so keep the inputs as-is until the
  // disclosure is closed by the user.
  useEffect(() => { setAcvpu(consciousness ?? 'A') }, [consciousness])
  useEffect(() => { setO2(!!on_oxygen) }, [on_oxygen])
  useEffect(() => { if (o2_flow_rate != null) setFlow(o2_flow_rate) }, [o2_flow_rate])

  async function push(fields, optimistic) {
    optimistic?.()
    setBusy(true); setErr(null)
    try {
      await setManualField({ patientId: patient_id, ...fields })
    } catch (e) {
      setErr(e.message ?? 'Save failed')
      console.warn('[manual]', fields, e)
    } finally {
      setBusy(false)
    }
  }

  function onAcvpu(e) {
    const v = e.target.value
    push({ acvpu: v }, () => setAcvpu(v))
  }

  function onO2Toggle(e) {
    const checked = e.target.checked
    const fields = { on_oxygen: checked }
    if (checked && flow) fields.o2_flow_rate = Number(flow)
    push(fields, () => setO2(checked))
  }

  function onFlowCommit() {
    const n = Number(flow)
    if (!Number.isFinite(n) || n < 0) return
    push({ on_oxygen: o2, o2_flow_rate: n })
  }

  function onOverrideSubmit(e) {
    e.preventDefault()
    const fields = {}
    const nbpS = Number(bpS), nbpD = Number(bpD), nT = Number(t)
    if (Number.isFinite(nbpS)) fields.bp_sys = nbpS
    if (Number.isFinite(nbpD)) fields.bp_dia = nbpD
    if (Number.isFinite(nT))   fields.temp_c = nT
    if (!Object.keys(fields).length) return
    push(fields)
  }

  function stop(e) { e.stopPropagation() }

  return (
    <div className="manual-controls" onClick={stop}>
      <label className="mc-field">
        <span className="mc-label">ACVPU</span>
        <select
          className="mc-select"
          value={acvpu}
          disabled={busy}
          onChange={onAcvpu}
          onClick={stop}
          aria-label="Set ACVPU level"
        >
          {ACVPU_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
        <FreshnessBadge setAt={acvpu_set_at} />
      </label>

      <label className="mc-field mc-field--toggle">
        <input
          type="checkbox"
          checked={o2}
          disabled={busy}
          onChange={onO2Toggle}
          onClick={stop}
          aria-label="Toggle supplemental oxygen"
        />
        <span className="mc-label">O₂</span>
        <FreshnessBadge setAt={o2_set_at} />
        {o2 && (
          <input
            type="number"
            className="mc-flow"
            min="0"
            step="0.5"
            value={flow}
            disabled={busy}
            onChange={e => setFlow(e.target.value)}
            onBlur={onFlowCommit}
            onKeyDown={e => { if (e.key === 'Enter') { e.target.blur() } }}
            onClick={stop}
            aria-label="Oxygen flow rate L/min"
          />
        )}
        {o2 && <span className="mc-unit">L/min</span>}
      </label>

      <details className="mc-override" onClick={stop}>
        <summary>Manual override</summary>
        <form className="mc-override-form" onSubmit={onOverrideSubmit}>
          <label className="mc-field">
            <span className="mc-label">BP</span>
            <input
              type="number" className="mc-num" placeholder="sys"
              value={bpS} onChange={e => setBpS(e.target.value)} onClick={stop}
            />
            <span className="mc-sep">/</span>
            <input
              type="number" className="mc-num" placeholder="dia"
              value={bpD} onChange={e => setBpD(e.target.value)} onClick={stop}
            />
          </label>
          <label className="mc-field">
            <span className="mc-label">Temp</span>
            <input
              type="number" step="0.1" className="mc-num" placeholder="°C"
              value={t} onChange={e => setT(e.target.value)} onClick={stop}
            />
          </label>
          <button type="submit" className="btn btn--ack mc-apply" disabled={busy}>
            Apply
          </button>
        </form>
      </details>

      {busy && <span className="mc-status">Saving…</span>}
      {err && !busy && <span className="mc-status mc-status--err" title={err}>Save failed</span>}
    </div>
  )
}

export default function PatientCard({ patient, onClick, onCallDoctor }) {
  const [acking, setAcking] = useState(false)
  const [acked, setAcked] = useState(false)
  const [calling, setCalling] = useState(false)
  const [called, setCalled] = useState(false)

  const p = patient.patients
  const age = getAge(p.date_of_birth)
  const { hr, bp_sys, bp_dia, spo2, temp_c, rr, flag, ai_note, last_updated,
          news2_score, news2_risk, on_oxygen, consciousness,
          nibp_set_at, temp_set_at, discharge_status } = patient

  async function handleAcknowledge(e) {
    e.stopPropagation()
    setAcking(true)
    try {
      await acknowledgeFlag(patient.patient_id)
    } catch { /* silent — mock mode */ }
    setAcked(true)
    setAcking(false)
  }

  async function handleCallDoctor(e) {
    e.stopPropagation()

    const defaultMsg = ai_note?.slice(0, 160) ?? `${flag} vitals, please review.`
    // Single-line inline prompt: Enter sends, Cancel uses the default.
    const custom = window.prompt(
      `Calling ${p.attending_doc} for Room ${p.room_number}.\n` +
      `Optional: add a short message the doctor will hear.\n` +
      `(Leave as-is and press OK to use the current AI note.)`,
      defaultMsg,
    )
    if (custom === null) {
      // nurse clicked Cancel — abort, no call placed.
      return
    }

    setCalling(true)
    const message = custom.trim() || defaultMsg
    const newCall = {
      patientId: patient.patient_id,
      doctorName: p.attending_doc,
      specialty: 'attending',
      reason: message,
      customMessage: message,
      urgency: 'urgent',
    }
    try {
      await callDoctor(newCall)
    } catch { /* silent — mock mode */ }
    onCallDoctor?.({ ...newCall, patients: p })
    setCalled(true)
    setCalling(false)
  }

  const discharged = discharge_status === 'completed'
  const cardClass = [
    'patient-card',
    `patient-card--${flag}`,
    acked && 'patient-card--acked',
    discharged && 'patient-card--discharged',
  ].filter(Boolean).join(' ')

  return (
    <div
      className={cardClass}
      onClick={onClick}
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick?.()}
      aria-label={`Patient ${p.full_name}, ${discharged ? 'discharged' : flag}`}
    >
      {discharged && (
        <div className="patient-card-discharged-overlay" aria-hidden="true">
          <span>Discharged · vitals frozen</span>
        </div>
      )}
      <div className="pcard-header">
        <div className="pcard-title-group">
          <span>{p.full_name}</span>
          <span className="pcard-sep"> · </span>
          <span>Room {p.room_number}</span>
          <span className="pcard-sep"> · </span>
          <span>{age}{p.sex}</span>
          <span className="pcard-sep"> · </span>
          <span>{p.primary_dx}</span>
        </div>
        <div className="pcard-badges">
          {news2_score != null && (
            <span className={`news2-badge news2-badge--${news2_risk ?? 'none'}`}>
              Score: {news2_score}
            </span>
          )}
          <FlagBadge flag={flag} />
          <DischargeBadge status={discharge_status} />
        </div>
      </div>

      <div className="vitals-row">
        <VitalCell category="HR"   value={hr}                    unit="bpm"  hi={hr > 120}      lo={hr < 50} />
        <VitalCell category="BP"   value={`${bp_sys}/${bp_dia}`} unit="mmHg" hi={bp_sys > 140}  lo={bp_sys < 90} setAt={nibp_set_at} />
        <VitalCell category="SpO₂" value={spo2}                  unit="%"    lo={spo2 < 95} />
        <VitalCell category="Temp" value={temp_c}                unit="°C"   hi={temp_c > 38.0} lo={temp_c < 36.0} setAt={temp_set_at} />
        {rr != null && (
          <VitalCell category="RR" value={rr} unit="/min" hi={rr > 25} lo={rr < 10} />
        )}
      </div>

      <ManualControls patient={patient} />

      <Sparkline
        patientId={patient.patient_id}
        lastUpdated={last_updated}
        flag={flag}
      />

      <div className="ai-note">
        <span className="ai-note-icon">✦</span>
        <span className="ai-note-text">{ai_note}</span>
      </div>

      <div className="pcard-footer">
        <div className="pcard-footer-left">
          {flag === 'critical' && !acked && !discharged && (
            <>
              {!called ? (
                <button
                  className="btn btn--call"
                  onClick={handleCallDoctor}
                  disabled={calling}
                >
                  {calling ? '…' : `Call ${p.attending_doc} ↗`}
                </button>
              ) : (
                <span className="called-banner">✓ Doctor notified</span>
              )}
              <button className="btn btn--ack" onClick={handleAcknowledge} disabled={acking}>
                {acking ? '…' : 'Acknowledge'}
              </button>
            </>
          )}
          {acked && <span className="acked-banner">✓ Acknowledged</span>}
        </div>
        <div className="pcard-sync">Updated {new Date(last_updated).toLocaleTimeString()}</div>
      </div>
    </div>
  )
}
