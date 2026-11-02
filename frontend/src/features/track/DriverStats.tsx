import { useEffect, useState } from 'react'
import { getDriverStats } from './api'
import type { DriverStat } from './types'

export function DriverStats({ driverId }: { driverId: string }) {
  const [stats, setStats] = useState<DriverStat[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    load()
  }, [driverId])

  async function load() {
    setLoading(true)
    try {
      const s = await getDriverStats(driverId)
      setStats(s)
    } catch {
      setStats([])
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading...</div>

  return (
    <section style={{ padding: 16 }}>
      <h2 style={{ margin: '0 0 12px' }}>Driver Stats</h2>
      {stats.length === 0 ? (
        <div style={{ color: '#888' }}>No stats yet</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {stats.map(s => (
            <div key={s.trackId} style={{ padding: 12, background: '#111', borderRadius: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>Track: {s.trackId}</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, fontSize: 14 }}>
                <div><span style={{ color: '#888' }}>Best:</span> {s.bestLapMs}ms</div>
                <div><span style={{ color: '#888' }}>Avg:</span> {s.avgLapMs}ms</div>
                <div><span style={{ color: '#888' }}>Consistency:</span> {s.consistency}%</div>
                <div><span style={{ color: '#888' }}>Sessions:</span> {s.sessionsCount}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
