import { useState, useEffect, useCallback } from 'react'
import {
  listWatches,
  createWatch,
  patchWatch,
  deleteWatch,
  checkAlerts,
  listNotifications,
  type FuelWatch,
  type FuelAlert,
} from './api'
import { fetchFuelPrices, type Station } from '@features/fuelPrice/api'

export default function WatchlistScreen() {
  const [watches, setWatches] = useState<FuelWatch[]>([])
  const [alerts, setAlerts] = useState<FuelAlert[]>([])
  const [stations, setStations] = useState<Station[]>([])
  const [state, setState] = useState<'WA' | 'QLD'>('WA')
  const [stationId, setStationId] = useState('')
  const [fuelType, setFuelType] = useState('ULP')
  const [threshold, setThreshold] = useState(5)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    const [w, a] = await Promise.all([listWatches(), listNotifications()])
    setWatches(w)
    setAlerts(a)
  }, [])

  useEffect(() => {
    refresh().catch(() => {})
    fetchFuelPrices(state).then((r) => setStations(r.stations)).catch(() => {})
  }, [refresh, state])

  async function add() {
    if (!stationId) return
    setLoading(true)
    try {
      await createWatch({
        station_id: stationId,
        state,
        fuel_type: fuelType,
        threshold_pct: threshold,
      })
      await refresh()
    } finally {
      setLoading(false)
    }
  }

  async function runCheck() {
    setLoading(true)
    try {
      await checkAlerts()
      await refresh()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: '0 0 8px', fontSize: 28 }}>Fuel Watchlist</h1>
        <p style={{ margin: 0, color: '#888' }}>Star servos, set a % price-move threshold, get notified.</p>
      </header>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={state} onChange={(e) => setState(e.target.value as 'WA' | 'QLD')}>
          <option value="WA">WA</option>
          <option value="QLD">QLD</option>
        </select>
        <select value={stationId} onChange={(e) => setStationId(e.target.value)}>
          <option value="">Select station</option>
          {stations.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} — {s.price_cpl?.toFixed(1)}¢
            </option>
          ))}
        </select>
        <input value={fuelType} onChange={(e) => setFuelType(e.target.value)} placeholder="Fuel type" style={{ width: 80 }} />
        <input
          type="number"
          value={threshold}
          onChange={(e) => setThreshold(Number(e.target.value))}
          style={{ width: 70 }}
        />
        <button onClick={add} disabled={loading || !stationId}>Add watch</button>
        <button onClick={runCheck} disabled={loading}>Check alerts</button>
      </div>

      <h3>Watches ({watches.length})</h3>
      {watches.map((w) => (
        <div
          key={w.id}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 16px',
            borderBottom: '1px solid #333',
          }}
        >
          <div>
            <div style={{ fontWeight: 600 }}>{w.station_name || w.station_id}</div>
            <div style={{ fontSize: 12, color: '#888' }}>
              {w.state} • {w.fuel_type} • threshold {w.threshold_pct}%
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={w.active}
              onChange={async (e) => {
                await patchWatch(w.id, { active: e.target.checked })
                await refresh()
              }}
            />
            <button
              onClick={async () => {
                await deleteWatch(w.id)
                await refresh()
              }}
            >
              Delete
            </button>
          </div>
        </div>
      ))}

      <h3 style={{ marginTop: 24 }}>Alerts ({alerts.length})</h3>
      {alerts.map((a, i) => (
        <div
          key={i}
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid #333',
            color: a.direction === 'up' ? '#f87171' : '#4ade80',
          }}
        >
          {a.station_name || a.station_id}: {a.previous_price} → {a.current_price} ({a.direction} {a.change_pct}%)
        </div>
      ))}
    </div>
  )
}


