/** Status and source pills. Owner: Jian. */
import type { DataSource } from '../../app/types.ts'
import { statusLabel, statusTone } from './format.ts'

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill pill-${statusTone(status)}`}>{statusLabel(status)}</span>
}

/** Every booking and option shows where its data comes from; mock data is always labeled simulated. */
export function SourcePill({ source }: { source: DataSource }) {
  return source === 'mock' ? (
    <span className="pill pill-sim">Mock · simulated</span>
  ) : (
    <span className="pill pill-accent">Duffel test</span>
  )
}
