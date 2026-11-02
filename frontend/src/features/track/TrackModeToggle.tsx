import { useState } from 'react'
import { enableTrackMode, getTrackCar } from './api'
import type { TrackCarProfile } from './types'

export function TrackModeToggle({ vehicleId, onEnabled }: { vehicleId: string; onEnabled?: (p: TrackCarProfile) => void }) {
  const [profile, setProfile] = useState<TrackCarProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [trackOnly, setTrackOnly] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const p = await getTrackCar(vehicleId)
      setProfile(p)
    } catch (e) {
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }

  async function enable() {
    setLoading(true)
    try {
      const p = await enableTrackMode(vehicleId, trackOnly)
      setProfile(p)
      onEnabled?.(p)
    } catch (e) {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  return (
    <section style={{ padding: 16, border: '1px solid #333', borderRadius: 8, marginTop: 16 }}>
      <h2 style={{ margin: '0 0 12px', fontSize: 18 }}>Track Mode</h2>
      {profile ? (
        <div style={{ color: '#4ade80' }}>
          Enabled {profile.trackOnly ? '(track-only)' : '(dual use)'}
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={trackOnly} onChange={(e) => setTrackOnly(e.target.checked)} />
            Track-only (no road service mixing)
          </label>
          <button onClick={enable} disabled={loading} style={{ padding: '8px 16px', minHeight: 44 }}>
            {loading ? 'Enabling...' : 'Enable Track Mode'}
          </button>
          <button onClick={load} disabled={loading} style={{ padding: '8px 16px', minHeight: 44 }}>
            Check
          </button>
        </div>
      )}
    </section>
  )
}
