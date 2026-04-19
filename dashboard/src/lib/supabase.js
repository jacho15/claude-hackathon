import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = supabaseUrl
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null

export async function fetchPatients() {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('patient_current_state')
    .select(`*, patients (id, room_number, full_name, date_of_birth, sex, primary_dx, attending_doc)`)
    .order('news2_score', { ascending: false })
  if (error) throw error
  return data ?? []
}

export async function fetchDoctorCalls() {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('doctor_calls')
    .select(`*, patients (full_name, room_number)`)
    .in('status', ['pending', 'notified'])
    .order('created_at', { ascending: false })
  if (error) throw error
  return data ?? []
}

export function subscribeToPatients(onUpdate) {
  if (!supabase) return () => {}
  const channel = supabase
    .channel('patient_current_state_changes')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'patient_current_state' }, async () => {
      onUpdate(await fetchPatients())
    })
    .subscribe()
  return () => supabase.removeChannel(channel)
}

export function subscribeToDoctorCalls(onUpdate) {
  if (!supabase) return () => {}
  const channel = supabase
    .channel('doctor_calls_changes')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'doctor_calls' }, async () => {
      onUpdate(await fetchDoctorCalls())
    })
    .subscribe()
  return () => supabase.removeChannel(channel)
}

const CALL_SERVER_URL =
  import.meta.env.VITE_CALL_SERVER_URL || 'http://localhost:8300'

/**
 * Ask the call-server to place a real Twilio call + insert the
 * doctor_calls row. Falls back to a direct Supabase insert if the
 * call-server isn't reachable, so the UI still works in mock-only mode.
 *
 * Returns the server response { placed, sid?, reason?, call_id, ... }.
 */
export async function callDoctor({ patientId, doctorName, specialty, reason, urgency = 'urgent', customMessage }) {
  try {
    const res = await fetch(`${CALL_SERVER_URL}/call-doctor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id: patientId,
        doctor_name: doctorName,
        specialty,
        reason,
        urgency,
        custom_message: customMessage,
      }),
    })
    if (res.ok) return await res.json()
    console.warn('[callDoctor] server returned', res.status, await res.text())
  } catch (err) {
    console.warn('[callDoctor] server unreachable, falling back to direct insert:', err)
  }

  if (!supabase) return { placed: false, reason: 'offline' }
  const { error } = await supabase.from('doctor_calls').insert({
    patient_id: patientId,
    doctor_name: doctorName,
    specialty,
    reason,
    urgency,
    status: 'pending',
  })
  if (error) throw error
  return { placed: false, reason: 'call-server unreachable' }
}

/**
 * Close the full escalation loop for a patient.
 *
 * 1. Mark any open `flags` rows resolved (so the Flag feed stops showing them).
 * 2. Close any still-open `doctor_calls` rows (status in pending/notified).
 *    Using 'completed' since the schema's CHECK constraint doesn't include
 *    'acknowledged'. Side effect: the nurse-station queue auto-clears via the
 *    existing realtime sub because fetchDoctorCalls() filters to pending+notified.
 */
export async function acknowledgeFlag(patientId) {
  if (!supabase) return
  const nowIso = new Date().toISOString()

  const flagsRes = await supabase
    .from('flags')
    .update({ acknowledged: true, ack_by: 'Nurse', ack_at: nowIso })
    .eq('patient_id', patientId)
    .eq('acknowledged', false)
  if (flagsRes.error) throw flagsRes.error

  const callsRes = await supabase
    .from('doctor_calls')
    .update({ status: 'completed', completed_at: nowIso })
    .eq('patient_id', patientId)
    .in('status', ['pending', 'notified'])
  if (callsRes.error) throw callsRes.error
}

/**
 * Pull the last `limit` vitals samples for one patient, oldest-first so a
 * sparkline renders left-to-right. Used by PatientCard's Sparkline for a
 * real audit trail instead of the old hard-coded demo array.
 */
export async function fetchPatientTrend(patientId, limit = 20) {
  if (!supabase || !patientId) return []
  const { data, error } = await supabase
    .from('vitals_readings')
    .select('hr, news2_score, recorded_at')
    .eq('patient_id', patientId)
    .order('recorded_at', { ascending: false })
    .limit(limit)
  if (error) throw error
  return (data ?? []).slice().reverse()
}
