import { apiFetch } from '@shared/utils'
import type { Booking, VehicleId } from '@shared/types'

export function listBookings(vehicleId: VehicleId) {
  return apiFetch<Booking[]>(`/api/v1/vehicles/${vehicleId}/bookings`)
}