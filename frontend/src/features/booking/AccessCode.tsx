/** Asks for the demo's access code when the server requires one (DEMO_ACCESS_CODE). Owner: Jian. */
import { useState, type FormEvent } from 'react'

export function AccessCode({ onSubmit, wrong }: { onSubmit: (code: string) => void; wrong: boolean }) {
  const [code, setCode] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (code.trim()) onSubmit(code.trim())
  }

  return (
    <form className="card access" onSubmit={submit}>
      <h1 className="card-title">Enter the access code</h1>
      <p className="muted">This demo is private. Ask the person who shared it for the code.</p>
      <div className="access-row">
        <label className="sr-only" htmlFor="access-code">Access code</label>
        <input
          id="access-code"
          className="access-input"
          value={code}
          autoComplete="off"
          autoFocus
          onChange={(e) => setCode(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={!code.trim()}>Continue</button>
      </div>
      {wrong && <p className="error-text" role="alert">That code didn't work. Check it and try again.</p>}
    </form>
  )
}
