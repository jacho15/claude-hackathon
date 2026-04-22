import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = supabaseUrl
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null

const STAFF_ENDPOINT_URL =
  import.meta.env.VITE_STAFF_ENDPOINT_URL ||
  'http://127.0.0.1:8101/staff/patient/manual'

const BED_ENDPOINT_URL =
  import.meta.env.VITE_BED_ENDPOINT_URL ||
  'http://127.0.0.1:8102/bed/reserve'

const DISCHARGE_ENDPOINT_URL =
  import.meta.env.VITE_DISCHARGE_ENDPOINT_URL ||
  'http://127.0.0.1:8103/discharge/start'

export function getNurseName() {
  if (typeof window === 'undefined') return 'Nurse'
  return window.localStorage?.getItem('nurseName') || 'Nurse'
}

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
 * POST a manual vital update to the floor-aggregator's staff endpoint (B3).
 * Pass only the fields the nurse touched; everything else is preserved.
 *
 * Accepted fields: acvpu, on_oxygen, spo2_scale, bp_sys, bp_dia, temp_c, o2_flow_rate.
 * Throws on validation / network errors so callers can roll back optimistic UI.
 */
export async function setManualField({ patientId, ...fields }) {
  if (!patientId) throw new Error('patientId required')
  const body = { patient_id: patientId, set_by: getNurseName(), ...fields }
  const res = await fetch(STAFF_ENDPOINT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json())?.error ?? '' } catch { /* ignore */ }
    throw new Error(`staff endpoint ${res.status}: ${detail || res.statusText}`)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// Phase 2: Bed Board + Discharge Drawer data access.
// ---------------------------------------------------------------------------

export async function fetchBeds() {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('beds')
    .select('*, patients (id, full_name, room_number, primary_dx)')
    .order('room_number', { ascending: true })
  if (error) throw error
  return data ?? []
}

export function subscribeToBeds(onUpdate) {
  if (!supabase) return () => {}
  const channel = supabase
    .channel('beds_changes')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'beds' }, async () => {
      onUpdate(await fetchBeds())
    })
    .subscribe()
  return () => supabase.removeChannel(channel)
}

export async function fetchDischargeWorkflows() {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('discharge_workflows')
    .select('*, patients (full_name, room_number, primary_dx)')
    .order('started_at', { ascending: false })
    .limit(20)
  if (error) throw error
  return data ?? []
}

export function subscribeToWorkflows(onUpdate) {
  if (!supabase) return () => {}
  const channel = supabase
    .channel('discharge_workflows_changes')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'discharge_workflows' }, async () => {
      onUpdate(await fetchDischargeWorkflows())
    })
    .on('postgres_changes', { event: '*', schema: 'public', table: 'discharge_summaries' }, async () => {
      // A new summary doesn't change the workflow row, but the
      // drawer UI keys off summaries — re-fetch keeps it fresh.
      onUpdate(await fetchDischargeWorkflows())
    })
    .subscribe()
  return () => supabase.removeChannel(channel)
}

export async function fetchDischargeSummaries(workflowId) {
  if (!supabase || !workflowId) return []
  const { data, error } = await supabase
    .from('discharge_summaries')
    .select('*')
    .eq('workflow_id', workflowId)
    .order('created_at', { ascending: true })
  if (error) throw error
  return data ?? []
}

export async function fetchTransferRequests() {
  if (!supabase) return []
  const { data, error } = await supabase
    .from('transfer_requests')
    .select('*')
    .order('created_at', { ascending: false })
    .limit(20)
  if (error) throw error
  return data ?? []
}

export function subscribeToTransferRequests(onUpdate) {
  if (!supabase) return () => {}
  const channel = supabase
    .channel('transfer_requests_changes')
    .on('postgres_changes', { event: '*', schema: 'public', table: 'transfer_requests' }, async () => {
      onUpdate(await fetchTransferRequests())
    })
    .subscribe()
  return () => supabase.removeChannel(channel)
}

/**
 * POST a bed reservation request to the bed agent's HTTP endpoint.
 * Returns { request_id, status } so the caller can track the
 * resulting transfer_request row.
 */
export async function reserveBed({ ward, urgency = 'urgent', reason, requestedBy = 'dashboard' } = {}) {
  if (!ward) throw new Error('ward required')
  const res = await fetch(BED_ENDPOINT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ward, urgency, reason, requested_by: requestedBy }),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json())?.error ?? '' } catch { /* ignore */ }
    throw new Error(`bed endpoint ${res.status}: ${detail || res.statusText}`)
  }
  return res.json()
}

/**
 * POST a manual discharge start to the discharge agent.
 * Used for nurse-initiated discharges, independent of bed pressure.
 */
export async function startDischarge({ patientId, language = 'es', requestedBy } = {}) {
  if (!patientId) throw new Error('patientId required')
  const body = {
    patient_id: patientId,
    language,
    requested_by: requestedBy ?? getNurseName(),
  }
  const res = await fetch(DISCHARGE_ENDPOINT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = ''
    try { detail = (await res.json())?.error ?? '' } catch { /* ignore */ }
    throw new Error(`discharge endpoint ${res.status}: ${detail || res.statusText}`)
  }
  return res.json()
}

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
