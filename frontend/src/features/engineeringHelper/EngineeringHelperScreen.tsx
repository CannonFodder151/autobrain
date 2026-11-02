import { useState } from 'react'
import { runEngineeringHelper, type EngineeringHelperResponse } from './api'

export function EngineeringHelperScreen() {
  const [result, setResult] = useState<string>('')
  const [full, setFull] = useState<EngineeringHelperResponse | null>(null)
  const [loading, setLoading] = useState(false)

  async function check() {
    setLoading(true)
    try {
      const r = await runEngineeringHelper({
        vehicle_id: 'VIN1234567890',
        engine_light_on: false,
        fault_codes: [],
        rego_valid: true,
        service_interval_km: 10000,
        ownership_status: 'registered',
      })
      setFull(r)
      setResult(r.primary.message)
    } catch (e) {
      setResult(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>VASS Engineering Helper</h1>
      <p style={{ color: '#94a3b8', maxWidth: 720, marginBottom: 16 }}>
        VASS is a state-aware engineering helper that understands vehicle state
        (engine light / fault codes, registration, service interval, ownership,
        fuel, EV/PHEV powertrain) and turns it into actionable, plain-English
        guidance for owners and mechanics. Deterministic fallback always
        produces an answer; an AI-assisted explanation is included when an AI
        model is available.
      </p>
      <button onClick={check} disabled={loading} style={{ padding: '10px 20px', marginBottom: 16 }}>
        {loading ? 'Loading…' : 'Check vehicle state'}
      </button>
      <p>{result}</p>
      {full && (
        <div style={{ marginTop: 16 }}>
          <h3>State breakdown</h3>
          <ul style={{ color: '#e5e7eb' }}>
            {full.guidances.map((g: { state: string; severity: string; title: string; message: string; actions: string[] }) => (
              <li key={g.state} style={{ marginBottom: 8 }}>
                <b style={{ color: g.severity === 'critical' ? '#f87171' : g.severity === 'warning' ? '#fbbf24' : '#34d399' }}>
                  {g.title}
                </b>{' '}
                — {g.message}
                {g.actions.length > 0 && (
                  <div style={{ color: '#94a3b8', marginLeft: 16 }}>
                    {g.actions.map((a: string, i: number) => (
                      <div key={i}>• {a}</div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
          {full.ai_explanation && (
            <div style={{ marginTop: 16, padding: 12, background: '#1e293b', borderRadius: 6 }}>
              <b>AI explanation:</b> {full.ai_explanation}
            </div>
          )}
        </div>
      )}
    </main>
  )
}