import { useEffect, useState } from 'react'
import { getPrepChecklist, updatePrepItem } from './api'
import type { PrepChecklist as PrepChecklistType, PrepChecklistItem } from './types'

const DEFAULT_ITEMS: PrepChecklistItem[] = [
  { key: 'fluids', done: false },
  { key: 'torque', done: false },
  { key: 'safety', done: false },
  { key: 'tyre_age', done: false },
]

export function PrepChecklist({ sessionId }: { sessionId: string }) {
  const [checklist, setChecklist] = useState<PrepChecklistType | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    load()
  }, [sessionId])

  async function load() {
    setLoading(true)
    try {
      const c = await getPrepChecklist(sessionId)
      setChecklist(c)
    } catch {
      setChecklist({ id: 'temp', sessionId, items: DEFAULT_ITEMS })
    } finally {
      setLoading(false)
    }
  }

  async function toggle(item: PrepChecklistItem) {
    const updated = { ...item, done: !item.done }
    try {
      const c = await updatePrepItem(sessionId, updated)
      setChecklist(c)
    } catch {
      if (checklist) {
        setChecklist({ ...checklist, items: checklist.items.map(i => i.key === item.key ? updated : i) })
      }
    }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading...</div>
  const items = checklist?.items || []
  const done = items.filter(i => i.done).length
  const pct = items.length ? Math.round((done / items.length) * 100) : 0

  return (
    <section style={{ padding: 16 }}>
      <h2 style={{ margin: '0 0 12px' }}>Pre-session Checklist</h2>
      <div style={{ marginBottom: 12, color: '#888' }}>{done}/{items.length} ({pct}%)</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {items.map(item => (
          <label key={item.key} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: '#111', borderRadius: 8, minHeight: 44 }}>
            <input type="checkbox" checked={item.done} onChange={() => toggle(item)} style={{ width: 20, height: 20 }} />
            <span style={{ textTransform: 'capitalize' }}>{item.key.replace('_', ' ')}</span>
          </label>
        ))}
      </div>
    </section>
  )
}
