import { useState } from 'react'
import { addLap } from './api'
import type { Lap, LapSector, TyrePressure, BrakeTemp } from './types'

const CORNERS: Array<'FL' | 'FR' | 'RL' | 'RR'> = ['FL', 'FR', 'RL', 'RR']

export function SessionLive({ sessionId }: { sessionId: string }) {
  const [laps, setLaps] = useState<Lap[]>([])
  const [lapNum, setLapNum] = useState(1)
  const [timeMs, setTimeMs] = useState(0)
  const [sectors, setSectors] = useState<LapSector[]>([])
  const [tyrePressures, setTyrePressures] = useState<TyrePressure[]>(CORNERS.map(c => ({ corner: c })))
  const [brakeTemps, setBrakeTemps] = useState<BrakeTemp[]>(CORNERS.map(c => ({ corner: c, tempC: 0 })))
  const [saving, setSaving] = useState(false)

  async function saveLap() {
    setSaving(true)
    try {
      const lap = await addLap(sessionId, {
        number: lapNum,
        timeMs,
        sectors,
        tyrePressures,
        brakeTemps,
      })
      setLaps([lap, ...laps])
      setLapNum(lapNum + 1)
      setTimeMs(0)
      setSectors([])
    } catch {
      const local: Lap = {
        id: `local-${Date.now()}`,
        sessionId,
        number: lapNum,
        timeMs,
        sectors,
        tyrePressures,
        brakeTemps,
      }
      setLaps([local, ...laps])
      setLapNum(lapNum + 1)
      setTimeMs(0)
      setSectors([])
    } finally {
      setSaving(false)
    }
  }

  return (
    <section style={{ padding: 16 }}>
      <h2 style={{ margin: '0 0 12px' }}>Session Live</h2>
      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))' }}>
        <div style={{ padding: 12, background: '#111', borderRadius: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Lap Entry</div>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
            Lap #
            <input type="number" value={lapNum} onChange={(e) => setLapNum(Number(e.target.value))} style={{ padding: 10, minHeight: 44 }} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
            Time (ms)
            <input type="number" value={timeMs} onChange={(e) => setTimeMs(Number(e.target.value))} style={{ padding: 10, minHeight: 44 }} />
          </label>
          <button onClick={saveLap} disabled={saving} style={{ padding: '10px 16px', minHeight: 44, width: '100%' }}>
            {saving ? 'Saving...' : 'Save Lap'}
          </button>
        </div>
        <div style={{ padding: 12, background: '#111', borderRadius: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Tyre Pressures</div>
          {tyrePressures.map((tp, i) => (
            <div key={tp.corner} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <span style={{ width: 30 }}>{tp.corner}</span>
              <input placeholder="cold" type="number" style={{ flex: 1, padding: 8, minHeight: 40 }} onChange={(e) => {
                const next = [...tyrePressures]
                next[i] = { ...next[i], cold: Number(e.target.value) }
                setTyrePressures(next)
              }} />
              <input placeholder="hot" type="number" style={{ flex: 1, padding: 8, minHeight: 40 }} onChange={(e) => {
                const next = [...tyrePressures]
                next[i] = { ...next[i], hot: Number(e.target.value) }
                setTyrePressures(next)
              }} />
            </div>
          ))}
        </div>
        <div style={{ padding: 12, background: '#111', borderRadius: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Brake Temps (°C)</div>
          {brakeTemps.map((bt, i) => (
            <div key={bt.corner} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
              <span style={{ width: 30 }}>{bt.corner}</span>
              <input type="number" value={bt.tempC} style={{ flex: 1, padding: 8, minHeight: 40 }} onChange={(e) => {
                const next = [...brakeTemps]
                next[i] = { ...next[i], tempC: Number(e.target.value) }
                setBrakeTemps(next)
              }} />
            </div>
          ))}
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <h3 style={{ margin: '0 0 8px' }}>Laps</h3>
        {laps.map(l => (
          <div key={l.id} style={{ padding: 10, borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between' }}>
            <span>Lap {l.number}</span>
            <span>{l.timeMs}ms</span>
          </div>
        ))}
      </div>
    </section>
  )
}
