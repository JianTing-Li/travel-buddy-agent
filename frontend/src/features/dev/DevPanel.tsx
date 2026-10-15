/**
 * Dev panel: create simulated bookings, simulate airline changes and set mock faults. Owner: Jian.
 *
 * Not part of the traveler's app and not in the PRD. It renders only when the build sets VITE_DEV_PANEL=true,
 * and the backend only answers when it was started as dev_app. Everything it creates is simulated.
 */
import { useState } from 'react'
import type { DevApi } from '../../app/dataSource.ts'
import { DEV_FAULTS } from '../../app/types.ts'

const SCENARIOS = [
  { value: '', label: 'Random booking' },
  { value: 'case_1', label: 'Case 1: cancellation, no extra cost' },
  { value: 'case_2', label: 'Case 2: missed flight' },
  { value: 'case_3', label: 'Case 3: group, conflicting limits' },
  { value: 'case_4', label: 'Case 4: embedded instructions' },
]
const DUFFEL_ROUTES = [
  { value: 'jfk_lax', label: 'JFK to LAX' },
  { value: 'lhr_ltn', label: 'LHR to LTN (Duffel can simulate airline changes here)' },
] as const
const MAX_SEED = 999_999
const NOT_AVAILABLE = "The dev endpoints aren't available. Start the backend as dev_app."

function problem(error: unknown): string {
  if (error instanceof Error && error.message && !error.message.startsWith('The server could not')) {
    return error.message === 'Not Found' ? NOT_AVAILABLE : error.message
  }
  return NOT_AVAILABLE
}

function Frame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card dev-panel" aria-label={title}>
      <div className="dev-head">
        <h2 className="card-title">{title}</h2>
        <span className="pill pill-sim">Dev tools · test data only</span>
      </div>
      {children}
    </section>
  )
}

/** On the bookings list: add a simulated booking to this session. */
export function DevCreatePanel({ dev, onCreated }: { dev: DevApi; onCreated: () => void }) {
  const [scenario, setScenario] = useState('')
  const [seed, setSeed] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [duffelRoute, setDuffelRoute] = useState<'jfk_lax' | 'lhr_ltn'>('lhr_ltn')

  async function createDuffel() {
    if (busy) return
    setError('')
    setMessage('')
    setBusy(true)
    try {
      const booking = await dev.createDuffelBooking({ route: duffelRoute, passengers: 1 })
      setMessage(`Created Duffel test booking ${booking.booking_id} (real test order, test balance).`)
      onCreated()
    } catch (e) {
      setError(problem(e))
    } finally {
      setBusy(false)
    }
  }

  async function create() {
    if (busy) return
    setError('')
    setMessage('')
    const trimmed = seed.trim()
    const parsed = trimmed === '' ? null : Number(trimmed)
    if (parsed !== null && (!Number.isInteger(parsed) || parsed < 0 || parsed > MAX_SEED)) {
      setError(`Enter a whole number from 0 to ${MAX_SEED}, or leave the seed empty.`)
      return
    }
    setBusy(true)
    try {
      const out = await dev.createBooking({ scenario: scenario || null, seed: parsed })
      setMessage(`Created ${out.booking.booking_id}. Seed ${out.seed} recreates it.`)
      onCreated()
    } catch (e) {
      setError(problem(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Frame title="Generate a test booking">
      <div className="dev-row">
        <label className="dev-field">
          <span className="small">Scenario</span>
          <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {SCENARIOS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
        <label className="dev-field">
          <span className="small">Seed (optional)</span>
          <input value={seed} inputMode="numeric" placeholder="e.g. 7" onChange={(e) => setSeed(e.target.value)} />
        </label>
        <button className="btn" type="button" onClick={create} aria-busy={busy}>
          {busy ? 'Creating…' : 'Generate test booking'}
        </button>
      </div>
      <div className="dev-row dev-duffel">
        <label className="dev-field">
          <span className="small">Duffel test order</span>
          <select value={duffelRoute} onChange={(e) => setDuffelRoute(e.target.value === 'jfk_lax' ? 'jfk_lax' : 'lhr_ltn')}>
            {DUFFEL_ROUTES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
        <button className="btn" type="button" onClick={createDuffel} aria-busy={busy}>
          {busy ? 'Creating…' : 'Create Duffel test booking'}
        </button>
      </div>
      {message && <p className="muted" role="status" style={{ marginTop: 8 }}>{message}</p>}
      {error && <p className="error-text" role="alert">{error}</p>}
    </Frame>
  )
}

/** On a booking page: simulate an airline change, or make the mock misbehave for this booking. */
export function DevBookingPanel({ dev, bookingId }: { dev: DevApi; bookingId: string }) {
  const [kind, setKind] = useState<'delay' | 'cancellation'>('delay')
  const [minutes, setMinutes] = useState('60')
  const [faults, setFaults] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<string>) {
    if (busy) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      setMessage(await action())
    } catch (e) {
      setError(problem(e))
    } finally {
      setBusy(false)
    }
  }

  const disrupt = () =>
    run(async () => {
      const delay = Number(minutes)
      if (kind === 'delay' && (!Number.isInteger(delay) || delay <= 0 || delay > 1440)) {
        throw new Error('Enter delay minutes from 1 to 1440.')
      }
      const change = await dev.disrupt(bookingId, { kind, delay_minutes: kind === 'delay' ? delay : 0 })
      return `Simulated: ${change.summary} The page finds it within a few seconds.`
    })

  const applyFaults = () =>
    run(async () => {
      const out = await dev.setFaults(bookingId, faults)
      return out.faults.length ? `Active faults: ${out.faults.join(', ')}.` : 'All faults cleared.'
    })

  function toggle(fault: string) {
    setFaults((current) => (current.includes(fault) ? current.filter((f) => f !== fault) : [...current, fault]))
  }

  return (
    <Frame title="Simulate on this booking">
      <div className="dev-row">
        <label className="dev-field">
          <span className="small">Airline change</span>
          <select value={kind} onChange={(e) => setKind(e.target.value === 'cancellation' ? 'cancellation' : 'delay')}>
            <option value="delay">Delay</option>
            <option value="cancellation">Cancellation</option>
          </select>
        </label>
        {kind === 'delay' && (
          <label className="dev-field">
            <span className="small">Minutes</span>
            <input value={minutes} inputMode="numeric" onChange={(e) => setMinutes(e.target.value)} />
          </label>
        )}
        <button className="btn" type="button" onClick={disrupt} aria-busy={busy}>Simulate airline change</button>
      </div>
      <fieldset className="dev-faults">
        <legend className="small">Mock faults for this booking</legend>
        {DEV_FAULTS.map((fault) => (
          <label key={fault} className="dev-check">
            <input type="checkbox" checked={faults.includes(fault)} onChange={() => toggle(fault)} />
            {fault}
          </label>
        ))}
        <button className="btn btn-small" type="button" onClick={applyFaults} aria-busy={busy}>Apply faults</button>
      </fieldset>
      {message && <p className="muted" role="status" style={{ marginTop: 8 }}>{message}</p>}
      {error && <p className="error-text" role="alert">{error}</p>}
    </Frame>
  )
}
