import { apiBase } from '@shared/utils'

export interface ReceiptResult {
  text: string
  total?: number | null
  litres?: number | null
  method: string
}

export async function scanReceipt(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${apiBase}/api/v1/receipts/scan`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<ReceiptResult>
}