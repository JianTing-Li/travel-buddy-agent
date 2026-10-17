/** Status and source pills. Owner: Jian. */
import type { DataSource } from '../../app/types.ts'
import { statusLabel, statusTone } from './format.ts'

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill pill-${statusTone(status)}`}>{statusLabel(status)}</span>
}

/** Where a booking or option comes from. Shown in dev mode only: the header badge already says the app is simulated. */
export function SourcePill({ source }: { source: DataSource }) {
  return source === 'mock' ? (
    <span className="pill pill-sim">Mock data</span>
  ) : (
    <span className="pill pill-accent">Duffel test</span>
  )
}
