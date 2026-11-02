import { apiFetch } from '@shared/utils'

export interface OwnershipAdvisorResult {
  mode: string
  value: number
  detail: string
  breakdown: Record<string, unknown>
}

export interface OwnershipAdvisorResponse {
  vehicle_id: string
  results: OwnershipAdvisorResult[]
  used_fallback: boolean
  ai_explanation?: string | null
}

export function runOwnershipAdvisor(payload: Record<string, unknown>) {
  return apiFetch<OwnershipAdvisorResponse>(`/api/v1/vehicles/${payload.vehicle_id}/ownership-advisor`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
