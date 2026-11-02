import { useEffect, useState } from 'react'
import type { Lap } from './types'

export function SessionSummary({ laps }: { laps?: Lap[] }) {
  const [data, setData] = useState<Lap[]>(laps || [])

  useEffect(() => {
    if (laps) setData(laps)
  }, [laps])

  if (!data.length) return <div style={{ padding: 16, color: '#888' }}>No laps yet</div>

  const times = data.map(l => l.timeMs)
  const best = Math.min(...times)
  const avg = Math.round(times.reduce((a,b) => a+b, 0) / times.length)
  const consistency = times.length > 1 ? Math.round((1 - (Math.max(...times)-Math.min(...times))/avg) * 100) : 100

  return (
    <section style={{ padding: 16 }}>
      <h2 style={{ margin: '0 0 12px' }}>Session Summary</h2>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <div style={{ padding: 16, background: '#111', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ color: '#888', fontSize: 12 }}>Best Lap</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: '#4ade80' }}>{best}ms</div>
        </div>
        <div style={{ padding: 16, background: '#111', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ color: '#888', fontSize: 12 }}>Avg Lap</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{avg}ms</div>
        </div>
        <div style={{ padding: 16, background: '#111', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ color: '#888', fontSize: 12 }}>Consistency</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{consistency}%</div>
        </div>
        <div style={{ padding: 16, background: '#111', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ color: '#888', fontSize: 12 }}>Laps</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{data.length}</div>
        </div>
      </div>
    </section>
  )
}
