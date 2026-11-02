import { apiFetch } from '@shared/utils'
import type {
  TrackCarProfile,
  TrackDaySession,
  Lap,
  PrepChecklist,
  PrepChecklistItem,
  ServiceEvent,
  DriverStat,
} from './types'
import type { VehicleId } from '@shared/types'

export function getTrackCar(vehicleId: VehicleId) {
  return apiFetch<TrackCarProfile | null>(`/api/track/cars/${vehicleId}`)
}

export function enableTrackMode(vehicleId: VehicleId, trackOnly = false) {
  return apiFetch<TrackCarProfile>('/api/track/cars', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ baseVehicleId: vehicleId, trackOnly }),
  })
}

export function listTrackSessions(carId: string) {
  return apiFetch<TrackDaySession[]>(`/api/track/cars/${carId}/sessions`)
}

export function createTrackSession(carId: string, data: Partial<TrackDaySession>) {
  return apiFetch<TrackDaySession>('/api/track/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ carId, ...data }),
  })
}

export function getTrackSession(sessionId: string) {
  return apiFetch<TrackDaySession>(`/api/track/sessions/${sessionId}`)
}

export function addLap(sessionId: string, lap: Omit<Lap, 'id' | 'sessionId'>) {
  return apiFetch<Lap>(`/api/track/sessions/${sessionId}/laps`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(lap),
  })
}

export function getPrepChecklist(sessionId: string) {
  return apiFetch<PrepChecklist>(`/api/track/sessions/${sessionId}/prep`)
}

export function updatePrepItem(sessionId: string, item: PrepChecklistItem) {
  return apiFetch<PrepChecklist>(`/api/track/sessions/${sessionId}/prep`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: [item] }),
  })
}

export function getServiceEvents(carId: string) {
  return apiFetch<ServiceEvent[]>(`/api/track/cars/${carId}/service`)
}

export function addServiceEvent(carId: string, event: Omit<ServiceEvent, 'id' | 'carId'>) {
  return apiFetch<ServiceEvent>(`/api/track/cars/${carId}/service`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(event),
  })
}

export function getDriverStats(driverId: string) {
  return apiFetch<DriverStat[]>(`/api/track/drivers/${driverId}/stats`)
}
