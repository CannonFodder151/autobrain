import { useState } from 'react'
import { getResaleEstimate, type ResaleResult } from './api'

export function ResaleEstimateScreen() {
  const [make, setMake] = useState('Toyota')
  const [model, setModel] = useState('Corolla')
  const [year, setYear] = useState('2019')
  const [mileage, setMileage] = useState('40000')
  const [res, setRes] = useState<ResaleResult | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const r = await getResaleEstimate({ make, model, year: Number(year), mileage: Number(mileage) })
    setRes(r)
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Resale Estimate</h1>
      <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input value={make} onChange={(e) => setMake(e.target.value)} />
        <input value={model} onChange={(e) => setModel(e.target.value)} />
        <input value={year} onChange={(e) => setYear(e.target.value)} />
        <input value={mileage} onChange={(e) => setMileage(e.target.value)} />
        <button type="submit">Estimate</button>
      </form>
      {res && (
        <div style={{ marginTop: 16 }}>
          <div>Estimated value: ${res.estimated_value}</div>
          <div>Trade-in: ${res.trade_in}</div>
          <div>Notes: {res.notes}</div>
        </div>
      )}
    </main>
  )
}