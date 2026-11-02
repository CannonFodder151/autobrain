import { useState } from 'react'
import { scanReceipt, type ReceiptResult } from './api'

export function ReceiptScanScreen() {
  const [res, setRes] = useState<ReceiptResult | null>(null)
  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) setRes(await scanReceipt(f))
  }
  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Receipt Scanning</h1>
      <input type="file" onChange={onChange} />
      {res && <pre>{JSON.stringify(res, null, 2)}</pre>}
    </main>
  )
}