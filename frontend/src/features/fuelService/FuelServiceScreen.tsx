import { useEffect, useState } from 'react'
import { addFuelFillUp, addServiceRecord, getEconomy, getSpending, listFuelFillUps, listServiceRecords, getTaxExportUrl } from './api'
import type { FuelFillUp, ServiceRecord } from './types'

export function FuelServiceScreen() {
  const [vehicleId, setVehicleId] = useState('VIN1234567890')
  const [fills, setFills] = useState<FuelFillUp[]>([])
  const [services, setServices] = useState<ServiceRecord[]>([])
  const [economy, setEconomy] = useState<any>(null)
  const [spending, setSpending] = useState<any>(null)
  const [businessUsePct, setBusinessUsePct] = useState(50)

  const load = async () => {
    const [f, s, e, sp] = await Promise.all([
      listFuelFillUps(vehicleId),
      listServiceRecords(vehicleId),
      getEconomy(vehicleId),
      getSpending(vehicleId),
    ])
    setFills(f)
    setServices(s)
    setEconomy(e)
    setSpending(sp)
  }

  useEffect(() => {
    load().catch(console.error)
  }, [])

  const submitFuel = async (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    const fd = new FormData(ev.currentTarget)
    await addFuelFillUp({
      vehicleId,
      date: String(fd.get('date')),
      litres: Number(fd.get('litres')),
      pricePerLitre: Number(fd.get('pricePerLitre')),
      odometer: Number(fd.get('odometer')),
      station: String(fd.get('station') || ''),
      fuelType: String(fd.get('fuelType') || 'ULP'),
    })
    ev.currentTarget.reset()
    load()
  }

  const submitService = async (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault()
    const fd = new FormData(ev.currentTarget)
    await addServiceRecord({
      vehicleId,
      date: String(fd.get('date')),
      mileage: Number(fd.get('mileage')),
      cost: Number(fd.get('cost')),
      items: String(fd.get('items') || '').split(',').map((x) => x.trim()).filter(Boolean),
    })
    ev.currentTarget.reset()
    load()
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif', maxWidth: 1000, margin: '0 auto' }}>
      <h1>Fuel & Service Tracking</h1>
      <div style={{ marginBottom: 16 }}>
        <label>Vehicle ID: </label>
        <input value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} />
        <button onClick={load} style={{ marginLeft: 8 }}>Refresh</button>
      </div>

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div>
          <h2>Log Fill-Up</h2>
          <form onSubmit={submitFuel} style={{ display: 'grid', gap: 8 }}>
            <input name="date" type="date" required />
            <input name="litres" type="number" step="0.01" placeholder="Litres" required />
            <input name="pricePerLitre" type="number" step="0.001" placeholder="Price/Litre" required />
            <input name="odometer" type="number" step="1" placeholder="Odometer" required />
            <input name="station" placeholder="Station" />
            <input name="fuelType" placeholder="Fuel Type" defaultValue="ULP" />
            <button type="submit">Add Fill-Up</button>
          </form>

          <h2>Log Service</h2>
          <form onSubmit={submitService} style={{ display: 'grid', gap: 8 }}>
            <input name="date" type="date" required />
            <input name="mileage" type="number" step="1" placeholder="Mileage" required />
            <input name="cost" type="number" step="0.01" placeholder="Cost" required />
            <input name="items" placeholder="Items (comma separated)" />
            <button type="submit">Add Service</button>
          </form>
        </div>

        <div>
          <h2>Spending Trends</h2>
          <pre>{JSON.stringify(spending, null, 2)}</pre>

          <h2>L/100km</h2>
          <pre>{JSON.stringify(economy, null, 2)}</pre>

          <h2>Tax Claim Export</h2>
          <label>Business use %: </label>
          <input type="number" value={businessUsePct} onChange={(e) => setBusinessUsePct(Number(e.target.value))} style={{ width: 60 }} />
          <a href={getTaxExportUrl(vehicleId, businessUsePct)} target="_blank" rel="noreferrer">Download CSV</a>

          <h2>Recent Fill-Ups</h2>
          <ul>
            {fills.slice(-5).map((f) => (
              <li key={f.id}>{f.date}: {f.litres}L @ {f.pricePerLitre} ({f.station || '-'}), {f.totalCost} total</li>
            ))}
          </ul>

          <h2>Recent Services</h2>
          <ul>
            {services.slice(-5).map((s) => (
              <li key={s.id}>{s.date} @ {s.mileage}km: {s.cost} ({s.items.join(', ')})</li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  )
}
