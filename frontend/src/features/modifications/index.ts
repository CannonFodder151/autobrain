import { apiFetch } from '@shared/utils'
import type { Modification, VehicleId } from '@shared/types'

export function listModifications(vehicleId: VehicleId) {
  return apiFetch<Modification[]>(`/api/v1/vehicles/${vehicleId}/modifications`)
}