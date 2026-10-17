/** Shows the option the traveler is about to confirm. Only the Confirm button here triggers a rebooking. Owner: Jian. */
import { useState } from 'react'
import type { ConfirmCard as ConfirmCardData } from '../../app/types.ts'
import { flightLabel, formatDateTime, formatMoney } from './format.ts'
import { SourcePill } from './Pills.tsx'

/** What a confirm attempt came back with, when it did not simply work. */
export type ConfirmProblem = { kind: 'error' | 'pending'; message: string }

interface Props {
  card: ConfirmCardData
  /** Dev mode: also show where the option comes from (mock or Duffel test). */
  showSource: boolean
  /** Resolves to null when it worked, or to the problem to show. */
  onConfirm: (optionId: string) => Promise<ConfirmProblem | null>
  /** Asks the app whether an uncertain rebooking went through. */
  onCheck: () => Promise<void>
  onDismiss: () => void
}

export function ConfirmCard({ card, showSource, onConfirm, onCheck, onDismiss }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState('')
  const { option } = card
  const d = option.flight_details
  const connections = typeof d.connections === 'number' ? d.connections : null
  const free = option.additional_cost === 0

  async function confirm() {
    if (busy) return
    setBusy(true)
    setError('')
    const problem = await onConfirm(option.option_id)
    if (problem?.kind === 'pending') setPending(problem.message)
    else if (problem) setError(problem.message)
    setBusy(false)
  }

  async function check() {
    if (busy) return
    setBusy(true)
    await onCheck()
    setBusy(false)
  }

  return (
    <section className="confirm" aria-labelledby="confirm-title">
      <div className="confirm-head">
        <h2 className="card-title" id="confirm-title" style={{ margin: 0 }}>Review your new flight</h2>
        {showSource && <SourcePill source={option.data_source} />}
      </div>
      <p className="route-line" style={{ fontSize: 20 }}>
        {String(d.origin ?? '')} to {String(d.destination ?? '')}
        <span className="pill pill-success">
          {connections === 0 ? 'Nonstop' : `${connections ?? '?'} connection${connections === 1 ? '' : 's'}`}
        </span>
      </p>
      <ul className="facts">
        <li><strong>{flightLabel(d.airline, d.flight)}</strong></li>
        <li>Departs {d.origin} · {formatDateTime(d.departs)}</li>
        <li>Arrives {d.destination} · {formatDateTime(d.arrives)}</li>
        {d.duration && <li>Flight time {d.duration}</li>}
      </ul>
      <div className="confirm-cost">
        <span>Extra cost for the whole booking</span>
        <strong>{formatMoney(option.additional_cost, option.currency)}</strong>
      </div>
      {free && <p className="muted">No extra payment needed.</p>}
      {card.changes_to_review.length > 0 && (
        <ul className="changes">
          {card.changes_to_review.map((change) => <li key={change}>{change}</li>)}
        </ul>
      )}
      <p className="small" style={{ marginTop: 8 }}>{card.notice}</p>
      {error && <p className="error-text" role="alert">{error}</p>}
      {pending ? (
        <div className="pending" role="status">
          <h3>Checking your rebooking</h3>
          <p>{pending}</p>
          <p className="small">Please don't book again yet. Nothing else will be booked until we know.</p>
          <div className="confirm-actions">
            <button className="btn" type="button" onClick={check} aria-busy={busy}>
              {busy ? 'Checking…' : 'Check status'}
            </button>
          </div>
        </div>
      ) : (
        <div className="confirm-actions">
          <button className="btn btn-primary" type="button" onClick={confirm} aria-busy={busy}>
            {busy ? 'Confirming…' : 'Confirm rebooking'}
          </button>
          <button className="btn" type="button" onClick={onDismiss}>Choose another</button>
        </div>
      )}
    </section>
  )
}
