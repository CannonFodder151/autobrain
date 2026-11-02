import { useState } from 'react'
import { runOwnershipAdvisor } from './api'

export function OwnershipAdvisorScreen() {
  const [result, setResult] = useState<string>('')
  const [loading, setLoading] = useState(false)

  async function check() {
    setLoading(true)
    try {
      const r = await runOwnershipAdvisor({
        vehicle_id: 'VIN1234567890',
        current_value: 18000,
        replacement_cost: 25000,
        upgrade_budget: 10000,
        interest_rate: 0.06,
        loan_term_months: 60,
        dream_price: 45000,
        dream_monthly_budget: 600,
      })
      setResult(r.results.map((x) => `${x.mode}: ${x.detail}`).join('\n'))
    } catch (e) {
      setResult(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Ownership Advisor</h1>
      <button onClick={check} disabled={loading} style={{ padding: '10px 20px', marginBottom: 16 }}>
        {loading ? 'Loading…' : 'Run advisor'}
      </button>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{result}</pre>
    </main>
  )
}
