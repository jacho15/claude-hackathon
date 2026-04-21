import { useState, useEffect, useRef } from 'react'
import PatientGrid from './components/PatientGrid'
import DoctorQueue from './components/DoctorQueue'
import BedBoard from './components/BedBoard'
import DischargeDrawer from './components/DischargeDrawer'
import EmergencyTrigger from './components/EmergencyTrigger'
import {
  fetchPatients,
  fetchDoctorCalls,
  fetchBeds,
  fetchDischargeWorkflows,
  subscribeToPatients,
  subscribeToDoctorCalls,
  subscribeToBeds,
  subscribeToWorkflows,
} from './lib/supabase'
import { MOCK_PATIENTS, MOCK_DOCTOR_CALLS } from './lib/mockData'
import './App.css'

const USE_MOCK = !import.meta.env.VITE_SUPABASE_URL

function useLiveClock() {
  const [time, setTime] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function App() {
  const [patients, setPatients] = useState(USE_MOCK ? MOCK_PATIENTS : [])
  const [doctorCalls, setDoctorCalls] = useState(USE_MOCK ? MOCK_DOCTOR_CALLS : [])
  const [beds, setBeds] = useState([])
  const [workflows, setWorkflows] = useState([])
  const [activeWorkflow, setActiveWorkflow] = useState(null)
  const [loading, setLoading] = useState(!USE_MOCK)
  const [lastSync, setLastSync] = useState(USE_MOCK ? 'mock data' : '—')
  const clock = useLiveClock()
  // IDs of workflows we've already announced via the drawer. Seeded
  // on first load with whatever Supabase already has so historical
  // discharges don't pop the drawer when the page mounts; subsequent
  // realtime inserts (the demo click) are the only thing that auto-
  // opens the drawer. The user can close it; we won't re-open the
  // same workflow.
  const seenWorkflowIds = useRef(new Set())
  const dismissedWorkflowIds = useRef(new Set())

  useEffect(() => {
    if (USE_MOCK) return

    async function loadInitial() {
      try {
        const [p, d, b, w] = await Promise.all([
          fetchPatients(),
          fetchDoctorCalls(),
          fetchBeds(),
          fetchDischargeWorkflows(),
        ])
        setPatients(p)
        setDoctorCalls(d)
        setBeds(b)
        setWorkflows(w)
        // Seed the seen-set with existing workflow ids so we don't
        // pop the drawer for stale history when the page mounts.
        for (const wf of w) seenWorkflowIds.current.add(wf.id)
        setLastSync('just now')
      } catch (e) {
        console.error('Failed to load data:', e)
      } finally {
        setLoading(false)
      }
    }

    loadInitial()

    const unsubPatients = subscribeToPatients(data => {
      setPatients(data)
      setLastSync('just now')
    })
    const unsubCalls = subscribeToDoctorCalls(setDoctorCalls)
    const unsubBeds = subscribeToBeds(setBeds)
    const unsubWorkflows = subscribeToWorkflows(data => {
      setWorkflows(data)
      // 1. Keep the open drawer in sync with the latest row.
      setActiveWorkflow(prev => prev ? data.find(w => w.id === prev.id) || prev : prev)
      // 2. Auto-open the drawer for the first in-flight workflow we
      //    haven't seen before. Skips ones the user already dismissed
      //    so closing the drawer is sticky for the duration of a run.
      const inFlight = ['initiated','summary_drafted','transport_booked','room_released']
      const fresh = data.find(w =>
        w.id &&
        inFlight.includes(w.status) &&
        !seenWorkflowIds.current.has(w.id) &&
        !dismissedWorkflowIds.current.has(w.id)
      )
      for (const wf of data) seenWorkflowIds.current.add(wf.id)
      if (fresh) setActiveWorkflow(fresh)
    })

    return () => {
      unsubPatients()
      unsubCalls()
      unsubBeds()
      unsubWorkflows()
    }
  }, [])

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-left">
          <div>
            <div className="floor-title">Floor 3 West — Nurse Station</div>
            <div className="floor-meta">Head nurse: A. Torres · {patients.length} patients</div>
          </div>
        </div>
        <div className="topbar-right">
          <div className="sync-status">
            <span className="sync-dot" />
            Last sync: {lastSync}
          </div>
          <div className="clock">{clock}</div>
          <div className="system-status">
            <span className="system-status-dot" />
            {USE_MOCK ? 'Mock data' : 'Live'}
          </div>
        </div>
      </header>

      <main className="main main--phase2">
        {loading ? (
          <div className="loading">Loading patient data…</div>
        ) : (
          <>
            <div className="main-top">
              <PatientGrid
                patients={patients}
                onCallDoctor={call => {
                  if (USE_MOCK) {
                    setDoctorCalls(prev => [{
                      id: String(Date.now()),
                      urgency: call.urgency ?? 'urgent',
                      status: 'pending',
                      doctor_name: call.doctorName,
                      specialty: call.specialty,
                      reason: call.reason,
                      created_at: new Date().toISOString(),
                      patients: call.patients,
                    }, ...prev])
                  }
                }}
              />
              <BedBoard
                beds={beds}
                workflows={workflows}
                onSelectWorkflow={setActiveWorkflow}
              />
            </div>
            <div className="main-bottom">
              <DoctorQueue calls={doctorCalls} />
              <EmergencyTrigger />
            </div>
          </>
        )}
      </main>

      <DischargeDrawer
        workflow={activeWorkflow}
        onClose={() => {
          // Sticky-dismiss: once the user closes the drawer for a
          // given workflow, don't reopen it on the next realtime
          // push (which would feel adversarial mid-stage).
          if (activeWorkflow?.id) {
            dismissedWorkflowIds.current.add(activeWorkflow.id)
          }
          setActiveWorkflow(null)
        }}
      />

      <footer className="footer">
        <span>Nucleus</span>
        <span>Press <kbd>C</kbd> to call doctor on selected patient</span>
      </footer>
    </div>
  )
}
