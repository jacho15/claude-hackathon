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

export async function callDoctor({ patientId, doctorName, specialty, reason, urgency = 'urgent' }) {
  if (!supabase) return
  const { error } = await supabase.from('doctor_calls').insert({
    patient_id: patientId,
    doctor_name: doctorName,
    specialty,
    reason,
    urgency,
    status: 'pending',
  })
  if (error) throw error
}

export async function acknowledgeFlag(patientId) {
  if (!supabase) return
  const { error } = await supabase
    .from('flags')
    .update({ acknowledged: true, ack_by: 'Nurse', ack_at: new Date().toISOString() })
    .eq('patient_id', patientId)
    .eq('acknowledged', false)
  if (error) throw error
}
