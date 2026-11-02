import { apiFetch } from '@shared/utils'
import type { VehicleId } from '@shared/types'

export interface EngineeringHelperResponse {
  vehicle_id: VehicleId
  guidances: Array<{ state: string; severity: string; title: string; message: string; actions: string[] }>
  primary: { state: string; severity: string; title: string; message: string; actions: string[] }
  ai_explanation?: string
  used_fallback: boolean
}

export function runEngineeringHelper(data: Record<string, unknown>) {
  const vehicleId = data.vehicle_id as string
  return apiFetch<EngineeringHelperResponse>(`/api/v1/vehicles/${vehicleId}/engineering-helper`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}