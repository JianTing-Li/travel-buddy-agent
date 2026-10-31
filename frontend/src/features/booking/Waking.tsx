/** Delayed loading hint for a demo server that may be starting. Owner: Jian. */
import { useEffect, useState } from 'react'

const HINT_AFTER_MS = 4000

export function WakingNote() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setShow(true), HINT_AFTER_MS)
    return () => window.clearTimeout(timer)
  }, [])
  if (!show) return null
  return (
    <div className="muted waking-note" role="status">
      <p><strong>Starting Travel Buddy…</strong></p>
      <p>This demo’s server may be waking up. The first visit can take about a minute.</p>
    </div>
  )
}
