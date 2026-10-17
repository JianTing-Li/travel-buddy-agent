/**
 * Dev panel: add test bookings, simulate airline changes, put a booking back to normal and set mock faults.
 * Owner: Jian.
 *
 * Not part of the traveler's app and not in the PRD. It renders only when the build sets VITE_DEV_PANEL=true,
 * and the backend only answers when it was started as dev_app. Everything it creates is simulated.
 */
import { useState } from 'react'
import type { DevApi } from '../../app/dataSource.ts'
import { DEV_FAULTS, type DataSource, type DevSituation } from '../../app/types.ts'

/** Generated bookings, by what happened to them, then the four PRD test cases. */
const SITUATIONS: { value: DevSituation; label: string }[] = [
  { value: 'on time', label: 'On time' },
  { value: 'canceled', label: 'Canceled by the airline' },
  { value: 'delayed', label: 'Delayed' },
  { value: 'missed', label: 'Missed flight' },
  { value: 'random', label: 'Random (canceled or missed)' },
]
const CASES = [
  { value: 'case_1', label: 'Case 1: canceled, no extra cost' },
  { value: 'case_2', label: 'Case 2: missed flight' },
  { value: 'case_3', label: 'Case 3: group with conflicting limits' },
  { value: 'case_4', label: 'Case 4: hidden instructions in the data' },
]
const DUFFEL_ROUTES = [
  { value: 'jfk_lax', label: 'New York to Los Angeles' },
  { value: 'lhr_ltn', label: 'London Heathrow to Luton (can simulate a delay)' },
] as const
/** What each mock fault does, in plain words. */
const FAULT_LABELS: Record<(typeof DEV_FAULTS)[number], string> = {
  unknown_eligibility: 'Eligibility unknown',
  wrong_currency: 'Prices in euros',
  unavailable_option: 'First option sold out',
  changed_details: 'Price rises after search',
  tool_failure: 'Search fails',
  uncertain_completion: 'Confirmation gets lost',
}
const MAX_SEED = 999_999
const NOT_AVAILABLE = "The dev tools aren't available. Start the backend as dev_app."

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
        <span className="pill pill-sim">Dev tools</span>
      </div>
      {children}
    </section>
  )
}

/** The result of the last action: a short note that fades in, or an error. */
function Outcome({ message, error }: { message: string; error: string }) {
  return (
    <>
      {message && <p className="dev-message" role="status" key={message}>{message}</p>}
      {error && <p className="error-text" role="alert">{error}</p>}
    </>
  )
}

/** Runs one action at a time and keeps its outcome. */
function useAction() {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
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
  return { busy, message, error, run, setError }
}

/** On the bookings list: add a test booking to this session, or start the session over. */
export function DevCreatePanel({ dev, onCreated, onReset }: { dev: DevApi; onCreated: () => void; onReset: () => void }) {
  const [choice, setChoice] = useState<string>('canceled')
  const [seed, setSeed] = useState('')
  const [duffelRoute, setDuffelRoute] = useState<'jfk_lax' | 'lhr_ltn'>('lhr_ltn')
  const [confirmingReset, setConfirmingReset] = useState(false)
  const { busy, message, error, run, setError } = useAction()

  function create() {
    const trimmed = seed.trim()
    const parsed = trimmed === '' ? null : Number(trimmed)
    if (parsed !== null && (!Number.isInteger(parsed) || parsed < 0 || parsed > MAX_SEED)) {
      setError(`Enter a whole number from 0 to ${MAX_SEED}, or leave the seed empty.`)
      return
    }
    const isCase = choice.startsWith('case_')
    void run(async () => {
      const out = await dev.createBooking(
        isCase ? { scenario: choice, seed: parsed } : { situation: choice as DevSituation, seed: parsed },
      )
      onCreated()
      return `Added ${out.booking.booking_id}. Seed ${out.seed} makes the same booking again.`
    })
  }

  const createDuffel = () =>
    run(async () => {
      const booking = await dev.createDuffelBooking({ route: duffelRoute, passengers: 1 })
      onCreated()
      return `Added Duffel test booking ${booking.booking_id}.`
    })

  const reset = () =>
    run(async () => {
      const out = await dev.reset()
      setConfirmingReset(false)
      onReset()
      return `Test data reset. ${out.booking_ids.length} bookings, as at the start.`
    })

  return (
    <Frame title="Add a test booking">
      <div className="dev-row">
        <label className="dev-field">
          <span className="small">What happened</span>
          <select value={choice} onChange={(e) => setChoice(e.target.value)}>
            <optgroup label="Generated booking">
              {SITUATIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </optgroup>
            <optgroup label="PRD test case">
              {CASES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </optgroup>
          </select>
        </label>
        <label className="dev-field">
          <span className="small">Seed (optional)</span>
          <input value={seed} inputMode="numeric" placeholder="e.g. 7" onChange={(e) => setSeed(e.target.value)} />
        </label>
        <button className="btn" type="button" onClick={create} aria-busy={busy}>{busy ? 'Adding…' : 'Add booking'}</button>
      </div>
      <div className="dev-row dev-section">
        <label className="dev-field">
          <span className="small">Duffel test booking (uses Duffel's test API)</span>
          <select value={duffelRoute} onChange={(e) => setDuffelRoute(e.target.value === 'jfk_lax' ? 'jfk_lax' : 'lhr_ltn')}>
            {DUFFEL_ROUTES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>
        <button className="btn" type="button" onClick={createDuffel} aria-busy={busy}>
          {busy ? 'Adding…' : 'Add Duffel booking'}
        </button>
      </div>
      <div className="dev-row dev-section">
        {confirmingReset ? (
          <>
            <span className="small">Removes added bookings and undoes every change, rebooking and chat.</span>
            <button className="btn btn-small" type="button" onClick={reset} aria-busy={busy}>
              {busy ? 'Resetting…' : 'Reset'}
            </button>
            <button className="btn btn-small" type="button" onClick={() => setConfirmingReset(false)}>Cancel</button>
          </>
        ) : (
          <button className="btn btn-small" type="button" onClick={() => setConfirmingReset(true)}>Reset test data</button>
        )}
      </div>
      <Outcome message={message} error={error} />
    </Frame>
  )
}

interface BookingPanelProps {
  dev: DevApi
  bookingId: string
  dataSource: DataSource
  /** The booking was put back to normal: its chat starts over. */
  onCleared: () => void
}

/** On a booking page: simulate an airline change, put the booking back to normal, or make the mock misbehave. */
export function DevBookingPanel({ dev, bookingId, dataSource, onCleared }: BookingPanelProps) {
  const mock = dataSource === 'mock'
  const [kind, setKind] = useState<'delay' | 'cancellation'>('delay')
  const [minutes, setMinutes] = useState('60')
  const [faults, setFaults] = useState<string[]>([])
  const { busy, message, error, run } = useAction()

  const disrupt = () =>
    run(async () => {
      const delay = Number(minutes)
      if (kind === 'delay' && (!Number.isInteger(delay) || delay <= 0 || delay > 1440)) {
        throw new Error('Enter a delay from 1 to 1440 minutes.')
      }
      const change = await dev.disrupt(bookingId, { kind, delay_minutes: kind === 'delay' ? delay : 0 })
      return `${change.summary} The page shows it within a few seconds.`
    })

  const clear = () =>
    run(async () => {
      await dev.clearDisruption(bookingId)
      setFaults([])
      onCleared()
      return 'Back to normal: on time, with a fresh chat.'
    })

  const applyFaults = () =>
    run(async () => {
      const out = await dev.setFaults(bookingId, faults)
      const names = out.faults.map((f) => FAULT_LABELS[f as keyof typeof FAULT_LABELS] ?? f)
      return names.length ? `Faults on: ${names.join(', ')}.` : 'All faults off.'
    })

  function toggle(fault: string) {
    setFaults((current) => (current.includes(fault) ? current.filter((f) => f !== fault) : [...current, fault]))
  }

  return (
    <Frame title="Test this booking">
      <div className="dev-row">
        <label className="dev-field">
          <span className="small">Airline change</span>
          <select value={kind} onChange={(e) => setKind(e.target.value === 'cancellation' ? 'cancellation' : 'delay')}>
            <option value="delay">Delay</option>
            {mock && <option value="cancellation">Cancellation</option>}
          </select>
        </label>
        {kind === 'delay' && mock && (
          <label className="dev-field">
            <span className="small">Minutes</span>
            <input value={minutes} inputMode="numeric" onChange={(e) => setMinutes(e.target.value)} />
          </label>
        )}
        <button className="btn" type="button" onClick={disrupt} aria-busy={busy}>Simulate change</button>
      </div>
      {mock ? (
        <>
          <div className="dev-row dev-section">
            <button className="btn btn-small" type="button" onClick={clear} aria-busy={busy}>Back to normal</button>
            <span className="small">On time again, with no changes, faults or rebooking, and a fresh chat.</span>
          </div>
          <fieldset className="dev-faults">
            <legend className="small">Make the mock misbehave</legend>
            {DEV_FAULTS.map((fault) => (
              <label key={fault} className="dev-check" title={fault}>
                <input type="checkbox" checked={faults.includes(fault)} onChange={() => toggle(fault)} />
                {FAULT_LABELS[fault]}
              </label>
            ))}
            <button className="btn btn-small" type="button" onClick={applyFaults} aria-busy={busy}>Apply</button>
          </fieldset>
        </>
      ) : (
        <p className="small dev-section">Duffel picks the delay itself and can't undo it, and faults are mock-only.</p>
      )}
      <Outcome message={message} error={error} />
    </Frame>
  )
}
