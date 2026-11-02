import { useEffect, useState } from 'react'
import { getServiceEvents } from './api'
import type { ServiceEvent } from './types'

export function ServiceIntervals({ carId }: { carId: string }) {
  const [events, setEvents] = useState<ServiceEvent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    load()
  }, [carId])

  async function load() {
    setLoading(true)
    try {
      const e = await getServiceEvents(carId)
      setEvents(e)
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading...</div>

  return (
    <section style={{ padding: 16 }}>
      <h2 style={{ margin: '0 0 12px' }}>Service Intervals (track hours)</h2>
      {events.length === 0 ? (
        <div style={{ color: '#888' }}>No service events</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {events.map(ev => (
            <div key={ev.id} style={{ padding: 12, background: '#111', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, textTransform: 'capitalize' }}>{ev.kind.replace('_', ' ')}</div>
                <div style={{ fontSize: 12, color: '#888' }}>Track hours: {ev.trackHours}</div>
              </div>
              <span style={{ color: ev.done ? '#4ade80' : '#fbbf24' }}>{ev.done ? 'Done' : 'Due'}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
