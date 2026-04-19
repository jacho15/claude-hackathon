// Mock data matching the seed in README — used when Supabase is not connected
export const MOCK_PATIENTS = [
  {
    patient_id: 'aaaaaaaa-0000-0000-0000-000000000001',
    hr: 128, bp_sys: 158, bp_dia: 94, spo2: 97.0, temp_c: 38.9, rr: 22,
    flag: 'critical',
    ai_note: 'HR elevated 22 min, trending up. BP above threshold. Possible sepsis onset. → Call attending.',
    last_updated: new Date().toISOString(),
    patients: {
      room_number: '301', full_name: 'Maria Gonzalez',
      date_of_birth: '1957-03-14', sex: 'F',
      primary_dx: 'Post-op abdominal surgery', attending_doc: 'Dr. Patel',
    },
  },
  {
    patient_id: 'aaaaaaaa-0000-0000-0000-000000000004',
    hr: 44, bp_sys: 110, bp_dia: 70, spo2: 91.0, temp_c: 36.8, rr: 16,
    flag: 'critical',
    ai_note: 'Bradycardia detected. SpO₂ dropped 4pt in 8 min. ECG shows irregular pattern. → Immediate review.',
    last_updated: new Date().toISOString(),
    patients: {
      room_number: '305', full_name: 'James Okafor',
      date_of_birth: '1970-01-30', sex: 'M',
      primary_dx: 'Cardiac observation — bradycardia', attending_doc: 'Dr. Reyes',
    },
  },
  {
    patient_id: 'aaaaaaaa-0000-0000-0000-000000000002',
    hr: 88, bp_sys: 122, bp_dia: 78, spo2: 93.0, temp_c: 37.9, rr: 19,
    flag: 'watch',
    ai_note: 'SpO₂ borderline. Temp mildly elevated. Stable trend for 40 min. Continue monitoring.',
    last_updated: new Date().toISOString(),
    patients: {
      room_number: '302', full_name: 'Lin Yao',
      date_of_birth: '1983-07-22', sex: 'F',
      primary_dx: 'Community-acquired pneumonia', attending_doc: 'Dr. Patel',
    },
  },
  {
    patient_id: 'aaaaaaaa-0000-0000-0000-000000000003',
    hr: 72, bp_sys: 118, bp_dia: 74, spo2: 99.0, temp_c: 36.6, rr: 15,
    flag: 'stable',
    ai_note: 'All vitals within range for 3h. Next medication: amoxicillin at 14:30.',
    last_updated: new Date().toISOString(),
    patients: {
      room_number: '303', full_name: 'David Mehta',
      date_of_birth: '1995-11-09', sex: 'M',
      primary_dx: 'Appendectomy (day 1 post-op)', attending_doc: 'Dr. Singh',
    },
  },
]

export const MOCK_DOCTOR_CALLS = [
  {
    id: '1', urgency: 'urgent', status: 'pending',
    doctor_name: 'Dr. Patel', specialty: 'attending',
    reason: 'Possible sepsis onset — HR & BP elevated',
    created_at: new Date(Date.now() - 3 * 60000).toISOString(),
    patients: { full_name: 'Maria Gonzalez', room_number: '301' },
  },
  {
    id: '2', urgency: 'urgent', status: 'pending',
    doctor_name: 'Dr. Reyes', specialty: 'cardiology',
    reason: 'Bradycardia + dropping SpO₂',
    created_at: new Date(Date.now() - 1 * 60000).toISOString(),
    patients: { full_name: 'James Okafor', room_number: '305' },
  },
  {
    id: '3', urgency: 'routine', status: 'pending',
    doctor_name: 'Dr. Patel', specialty: 'attending',
    reason: 'Routine SpO₂ check',
    scheduled_at: new Date().toISOString().slice(0, 10) + 'T14:00:00',
    created_at: new Date(Date.now() - 30 * 60000).toISOString(),
    patients: { full_name: 'Lin Yao', room_number: '302' },
  },
  {
    id: '4', urgency: 'follow_up', status: 'pending',
    doctor_name: 'Dr. Singh', specialty: 'surgical',
    reason: 'Post-op follow-up day 1',
    scheduled_at: new Date().toISOString().slice(0, 10) + 'T15:30:00',
    created_at: new Date(Date.now() - 60 * 60000).toISOString(),
    patients: { full_name: 'David Mehta', room_number: '303' },
  },
]
