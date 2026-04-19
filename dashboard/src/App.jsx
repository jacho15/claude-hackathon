import { useState, useEffect } from 'react'
import PatientGrid from './components/PatientGrid'
import DoctorQueue from './components/DoctorQueue'
import { fetchPatients, fetchDoctorCalls, subscribeToPatients, subscribeToDoctorCalls } from './lib/supabase'
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
  const [loading, setLoading] = useState(!USE_MOCK)
  const [lastSync, setLastSync] = useState(USE_MOCK ? 'mock data' : '—')
  const clock = useLiveClock()

  useEffect(() => {
    if (USE_MOCK) return

    async function loadInitial() {
      try {
        const [p, d] = await Promise.all([fetchPatients(), fetchDoctorCalls()])
        setPatients(p)
        setDoctorCalls(d)
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

    return () => { unsubPatients(); unsubCalls() }
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

      <main className="main">
        {loading ? (
          <div className="loading">Loading patient data…</div>
        ) : (
          <>
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
            <DoctorQueue calls={doctorCalls} />
          </>
        )}
      </main>

      <footer className="footer">
        <span>Nucleus</span>
        <span>Press <kbd>C</kbd> to call doctor on selected patient</span>
      </footer>
    </div>
  )
}
