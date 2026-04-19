const URGENCY_LABEL = { urgent: 'Urgent', routine: 'Routine', follow_up: 'Follow-up' }

function timeAgo(iso) {
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000)
  if (mins < 1) return 'just now'
  if (mins === 1) return '1 min ago'
  return `${mins} min ago`
}

function scheduledTime(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function DoctorQueue({ calls }) {
  if (calls.length === 0) {
    return (
      <div className="queue-section">
        <div className="section-label">Doctor call queue</div>
        <div className="queue-empty">No pending calls</div>
      </div>
    )
  }

  return (
    <div className="queue-section">
      <div className="section-label">Doctor call queue</div>
      <div className="queue">
        {calls.map(call => {
          const scheduled = scheduledTime(call.scheduled_at)
          return (
            <div key={call.id} className="queue-item">
              <div className="qi-info">
                <div className="qi-patient">
                  {call.patients.full_name} · Room {call.patients.room_number}
                </div>
                <div className="qi-doctor">{call.doctor_name} ({call.specialty})</div>
                {call.reason && <div className="qi-reason">{call.reason}</div>}
              </div>
              <div className="qi-right">
                <span className={`flag-badge flag-badge--${call.urgency === 'urgent' ? 'critical' : call.urgency === 'routine' ? 'watch' : 'stable'}`}>
                  {URGENCY_LABEL[call.urgency]}
                </span>
                <div className="qi-time">
                  {scheduled ? `Scheduled ${scheduled}` : timeAgo(call.created_at)}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
