import { useState } from 'react'
import { TrackModeToggle } from './TrackModeToggle'

export function TrackScreen() {
  const [vehicleId, setVehicleId] = useState('VIN1234567890')
  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Track Car Mode</h1>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
        <label>Vehicle ID</label>
        <input value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} style={{ padding: 8 }} />
      </div>
      <TrackModeToggle vehicleId={vehicleId} />
    </main>
  )
}
