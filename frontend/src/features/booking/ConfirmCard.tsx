/** Shows the option the traveler is about to confirm. Only the Confirm button here triggers a rebooking. Owner: Jian. */
import { useState } from 'react'
import type { ConfirmCard as ConfirmCardData } from '../../app/types.ts'
import { formatLocalTime, formatMoney } from './format.ts'
import { SourcePill } from './Pills.tsx'

interface Props {
  card: ConfirmCardData
  /** Resolves to an error message to show, or null when it worked. */
  onConfirm: (optionId: string) => Promise<string | null>
  onDismiss: () => void
}

export function ConfirmCard({ card, onConfirm, onDismiss }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const { option } = card
  const d = option.flight_details
  const connections = typeof d.connections === 'number' ? d.connections : null
  const free = option.additional_cost === 0

  async function confirm() {
    if (busy) return
    setBusy(true)
    setError('')
    const problem = await onConfirm(option.option_id)
    if (problem) {
      setError(problem)
      setBusy(false)
    }
  }

  return (
    <section className="confirm" aria-labelledby="confirm-title">
      <div className="confirm-head">
        <h2 className="card-title" id="confirm-title" style={{ margin: 0 }}>Review your new flight</h2>
        <SourcePill source={option.data_source} />
      </div>
      <p className="route-line" style={{ fontSize: 20 }}>
        {String(d.origin ?? '')} to {String(d.destination ?? '')}
        <span className="pill pill-success">
          {connections === 0 ? 'Nonstop' : `${connections ?? '?'} connection${connections === 1 ? '' : 's'}`}
        </span>
      </p>
      <ul className="facts">
        <li><strong>{String(d.airline ?? 'Airline')}</strong> · {String(d.flight ?? '')}</li>
        <li>Departs {formatLocalTime(d.departs)}</li>
        <li>Arrives {formatLocalTime(d.arrives)}</li>
        <li>Duration {String(d.duration ?? 'unknown')}</li>
      </ul>
      <div className="confirm-cost">
        <span>Additional cost, whole booking</span>
        <strong>{formatMoney(option.additional_cost, option.currency)}</strong>
      </div>
      {free && <p className="muted">No additional payment required.</p>}
      {card.changes_to_review.length > 0 && (
        <ul className="changes">
          {card.changes_to_review.map((change) => <li key={change}>{change}</li>)}
        </ul>
      )}
      <p className="small" style={{ marginTop: 8 }}>{card.notice}</p>
      {error && <p className="error-text" role="alert">{error}</p>}
      <div className="confirm-actions">
        <button className="btn btn-primary" type="button" onClick={confirm} aria-busy={busy}>
          {busy ? 'Confirming…' : 'Confirm rebooking'}
        </button>
        <button className="btn" type="button" onClick={onDismiss}>Choose another</button>
      </div>
    </section>
  )
}
