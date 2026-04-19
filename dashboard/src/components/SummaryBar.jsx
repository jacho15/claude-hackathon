export default function SummaryBar({ patients }) {
  const critical = patients.filter(p => p.flag === 'critical').length
  const watch    = patients.filter(p => p.flag === 'watch').length
  const stable   = patients.filter(p => p.flag === 'stable').length

  return (
    <div className="summary-bar">
      <Stat label="Critical"       value={critical}         variant="critical" />
      <Stat label="Watch"          value={watch}            variant="watch" />
      <Stat label="Stable"         value={stable}           variant="stable" />
      <Stat label="Total patients" value={patients.length}  variant="neutral" />
    </div>
  )
}

function Stat({ label, value, variant }) {
  return (
    <div className={`stat-card stat-card--${variant}`}>
      <div className="stat-accent" />
      <div className="stat-body">
        <span className="stat-value">{value}</span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  )
}
