import { apiFetch } from '@shared/utils'

export interface ResaleResult {
  make: string
  model: string
  year: number
  mileage: number
  estimated_value: number
  trade_in: number
  depreciation_rate: number
  notes: string
}

export function getResaleEstimate(q: Record<string, string | number>) {
  const params = new URLSearchParams(q as any).toString()
  return apiFetch<ResaleResult>(`/api/v1/resale/estimate?${params}`)
}