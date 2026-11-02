import { useState } from 'react'
import { lookupRego, type RegoResult } from './api'

export function RegoLookupScreen() {
  const [rego, setRego] = useState('ABC123')
  const [state, setState] = useState('NSW')
  const [res, setRes] = useState<RegoResult | null>(null)
  const [err, setErr] = useState('')

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    try {
      const r = await lookupRego(rego, state)
      setRes(r)
    } catch (e: any) {
      setErr(String(e))
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Free Rego Lookup</h1>
      <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8 }}>
        <input value={rego} onChange={(e) => setRego(e.target.value)} placeholder="Rego" />
        <select value={state} onChange={(e) => setState(e.target.value)}>
          <option>NSW</option><option>VIC</option><option>QLD</option><option>SA</option><option>WA</option><option>TAS</option><option>NT</option><option>ACT</option>
        </select>
        <button type="submit">Lookup</button>
      </form>
      {err && <p style={{ color: 'red' }}>{err}</p>}
      {res && (
        <div style={{ marginTop: 16 }}>
          <div>VIN: {res.vin || '-'}</div>
          <div>Body: {res.body || '-'}</div>
          <div>Colour: {res.colour || '-'}</div>
          <div>Status: {res.status}</div>
          <div>Make/Model: {res.make || '-'} {res.model || '-'}</div>
        </div>
      )}
    </main>
  )
}