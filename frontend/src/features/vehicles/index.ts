import { apiFetch } from '@shared/utils'
import type { VehicleHealth, VehicleId, EngineeringHelperSummary } from '@shared/types'

export function getVehicleHealth(vehicleId: VehicleId) {
  return apiFetch<VehicleHealth>(`/api/v1/vehicles/${vehicleId}/health-score`)
}

export function getEngineeringHelper(vehicleId: VehicleId, state: Record<string, unknown>) {
  return apiFetch<EngineeringHelperSummary>(`/api/v1/vehicles/${vehicleId}/engineering-helper`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vehicle_id: vehicleId, ...state }),
  })
}