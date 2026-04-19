import PatientCard from './PatientCard'
import SummaryBar from './SummaryBar'

const FLAG_ORDER = { critical: 0, watch: 1, stable: 2 }

function sortByPriority(patients) {
  return [...patients].sort((a, b) => FLAG_ORDER[a.flag] - FLAG_ORDER[b.flag])
}

export default function PatientGrid({ patients, onSelectPatient, onCallDoctor }) {
  const sorted = sortByPriority(patients)

  if (patients.length === 0) {
    return (
      <div className="grid-empty">
        <span>No patient data — waiting for agent updates…</span>
      </div>
    )
  }

  return (
    <div className="patient-grid-section">
      <SummaryBar patients={patients} />
      <div className="section-label">Patients — sorted by priority</div>
      <div className="patient-grid">
        {sorted.map(patient => (
          <PatientCard
            key={patient.patient_id}
            patient={patient}
            onClick={() => onSelectPatient?.(patient)}
            onCallDoctor={onCallDoctor}
          />
        ))}
      </div>
    </div>
  )
}
