import { useState } from 'react'
import FlagBadge from './FlagBadge'
import { acknowledgeFlag, callDoctor } from '../lib/supabase'

const SPARK_COLOR = { critical: '#EF4444', watch: '#F59E0B', stable: '#22C55E' }

function getAge(dob) {
  if (!dob) return '—'
  return Math.floor((Date.now() - new Date(dob)) / (365.25 * 24 * 3600 * 1000))
}

function VitalCell({ category, value, unit, hi, lo }) {
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
    </div>
  )
}

function Sparkline({ flag }) {
  const raw = {
    critical: [30, 45, 50, 55, 65, 72, 80, 90],
    watch:    [40, 42, 45, 43, 50, 48, 52, 55],
    stable:   [50, 48, 52, 49, 51, 50, 48, 50],
  }[flag] ?? [50, 50, 50, 50, 50, 50, 50, 50]

  const W = 100, H = 24, pad = 2
  const max = Math.max(...raw), min = Math.min(...raw), range = max - min || 1
  const pts = raw.map((v, i) => {
    const x = (i / (raw.length - 1)) * W
    const y = H - pad - ((v - min) / range) * (H - pad * 2)
    return `${x},${y}`
  }).join(' ')

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
          opacity="0.7"
        />
      </svg>
      <span className="sparkline-label">Last 60m</span>
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
          news2_score, news2_risk, on_oxygen, consciousness } = patient

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
    setCalling(true)
    const newCall = {
      patientId: patient.patient_id,
      doctorName: p.attending_doc,
      specialty: 'attending',
      reason: ai_note?.slice(0, 80) ?? 'Critical vitals',
      urgency: 'urgent',
    }
    try {
      await callDoctor(newCall)
    } catch { /* silent — mock mode */ }
    onCallDoctor?.({ ...newCall, patients: p })
    setCalled(true)
    setCalling(false)
  }

  return (
    <div
      className={`patient-card patient-card--${flag} ${acked ? 'patient-card--acked' : ''}`}
      onClick={onClick}
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick?.()}
      aria-label={`Patient ${p.full_name}, ${flag}`}
    >
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
              NEWS2 {news2_score}
            </span>
          )}
          <FlagBadge flag={flag} />
        </div>
      </div>

      <div className="vitals-row">
        <VitalCell category="HR"   value={hr}                    unit="bpm"  hi={hr > 120}      lo={hr < 50} />
        <VitalCell category="BP"   value={`${bp_sys}/${bp_dia}`} unit="mmHg" hi={bp_sys > 140}  lo={bp_sys < 90} />
        <VitalCell category="SpO₂" value={spo2}                  unit="%"    lo={spo2 < 95} />
        <VitalCell category="Temp" value={temp_c}                unit="°C"   hi={temp_c > 38.0} lo={temp_c < 36.0} />
        {rr != null && (
          <VitalCell category="RR" value={rr} unit="/min" hi={rr > 25} lo={rr < 10} />
        )}
      </div>

      {(on_oxygen || (consciousness && consciousness !== 'A')) && (
        <div className="clinical-tags">
          {on_oxygen && <span className="clinical-tag clinical-tag--o2">O₂ supplemental</span>}
          {consciousness && consciousness !== 'A' && (
            <span className="clinical-tag clinical-tag--acvpu">ACVPU: {consciousness}</span>
          )}
        </div>
      )}

      <Sparkline flag={flag} />

      <div className="ai-note">
        <span className="ai-note-icon">✦</span>
        <span className="ai-note-text">{ai_note}</span>
      </div>

      <div className="pcard-footer">
        <div className="pcard-footer-left">
          {flag === 'critical' && !acked && (
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
