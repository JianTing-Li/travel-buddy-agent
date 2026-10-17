/**
 * Options from a search that code checked against the traveler's limits, as cards under Travel Buddy's reply.
 * Owner: Cheich (built by Jian with his OK).
 *
 * Everything shown comes from the search result, never from the model's text. Choosing a card only sends a chat
 * message; Travel Buddy then re-checks the option and the confirm card appears. Nothing here can book.
 */
import type { ExcludedOption, Limits, Option, SearchResults } from '../../app/types.ts'
import { flightLabel, formatMoney, formatTime } from '../booking/format.ts'

interface Props {
  search: SearchResults
  /** The option the traveler picked from these cards, if any. */
  chosen?: string
  /** False while a reply is on its way, or when newer results replaced these. */
  active: boolean
  onChoose: (option: Option) => void
}

export function OptionCards({ search, chosen, active, onChoose }: Props) {
  const { options, excluded, limits } = search
  const fits = options.length
  return (
    <div className="option-cards">
      <p className="option-cards-title">
        {fits === 0 ? 'No flights fit all your limits' : fits === 1 ? '1 flight fits your limits' : `${fits} flights fit your limits`}
      </p>
      {fits > 0 && (
        <ul className="option-list">
          {options.map((option, i) => (
            <OptionCard
              key={option.option_id}
              option={option}
              index={i}
              chosen={chosen === option.option_id}
              disabled={!active || (chosen !== undefined && chosen !== option.option_id)}
              onChoose={() => onChoose(option)}
            />
          ))}
        </ul>
      )}
      {excluded.length > 0 && (
        <details className="option-excluded" open={fits === 0}>
          <summary>
            {excluded.length === 1 ? "1 flight didn't fit" : `${excluded.length} flights didn't fit`}
          </summary>
          <ul>
            {excluded.map((e) => (
              <li key={e.option_id}>
                Lands {formatTime(e.arrives)} · {stops(e.connections)} · {cost(e.additional_cost, e.currency)}
                <span className="option-why"> — {e.reasons.map((r) => reasonText(r, e, limits)).join('; ')}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

interface CardProps {
  option: Option
  index: number
  chosen: boolean
  disabled: boolean
  onChoose: () => void
}

function OptionCard({ option, index, chosen, disabled, onChoose }: CardProps) {
  const d = option.flight_details
  return (
    <li className={`option-card${chosen ? ' option-card--chosen' : ''}`} style={{ animationDelay: `${index * 60}ms` }}>
      <div className="option-main">
        <p className="option-times">
          <strong>{formatTime(d.departs)}</strong> {d.origin}
          <span className="option-arrow" aria-hidden="true">→</span>
          <strong>{formatTime(d.arrives)}</strong> {d.destination}
        </p>
        <p className="small">
          {flightLabel(d.airline, d.flight)}{d.duration ? ` · ${d.duration}` : ''} · {stops(d.connections)}
        </p>
      </div>
      <p className={`option-cost${option.additional_cost === 0 ? ' option-cost--free' : ''}`}>
        {cost(option.additional_cost, option.currency)}
      </p>
      <button className="btn btn-small" type="button" onClick={onChoose} disabled={disabled || chosen} aria-pressed={chosen}>
        {chosen ? 'Chosen' : 'Choose'}
      </button>
    </li>
  )
}

function stops(connections: number): string {
  return connections === 0 ? 'Nonstop' : `${connections} connection${connections === 1 ? '' : 's'}`
}

function cost(amount: number, currency: string): string {
  return amount === 0 ? 'No extra cost' : `+${formatMoney(amount, currency)}`
}

/** The code's reason, said the way a traveler would. Unknown reasons are shown as they are. */
function reasonText(reason: string, e: ExcludedOption, limits: Limits): string {
  if (reason.startsWith('arrives after')) return `lands after your ${formatTime(limits.arrive_by)} deadline`
  if (reason.startsWith('additional cost is over')) {
    return limits.budget_additional_cost === 0
      ? 'costs extra, and you asked for no extra cost'
      : `costs more than your ${formatMoney(limits.budget_additional_cost, limits.currency)} limit`
  }
  if (reason.startsWith('has more connections')) {
    return limits.max_connections === 0 ? 'has a connection, and you asked for nonstop' : 'has too many connections'
  }
  if (reason.startsWith('priced in')) return `priced in ${e.currency}, not ${limits.currency}`
  if (reason.startsWith('eligibility') || reason.startsWith('option is')) return "can't be booked right now"
  return reason
}
