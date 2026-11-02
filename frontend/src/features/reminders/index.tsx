import { useEffect, useState } from 'react'
import { createReminder, listReminders, type Reminder } from './api'

export function RemindersScreen() {
  const [vehicleId, setVehicleId] = useState('VIN1234567890')
  const [items, setItems] = useState<Reminder[]>([])
  const load = async () => setItems(await listReminders(vehicleId))
  useEffect(() => { load().catch(console.error) }, [])

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const fd = new FormData(e.currentTarget)
    await createReminder({ vehicleId, kind: String(fd.get('kind')), dueDate: String(fd.get('dueDate')), message: String(fd.get('message') || '') })
    e.currentTarget.reset()
    load()
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Service Reminders</h1>
      <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8 }}>
        <input name="kind" placeholder="kind" />
        <input name="dueDate" type="date" />
        <input name="message" placeholder="message" />
        <button type="submit">Add reminder</button>
      </form>
      <ul>{items.map(r => <li key={r.id}>{r.kind} - {r.dueDate} {r.message}</li>)}</ul>
    </main>
  )
}