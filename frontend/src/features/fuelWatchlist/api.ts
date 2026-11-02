export interface FuelWatch {
  id: string
  user_id: string
  station_id: string
  station_name?: string | null
  state: string
  fuel_type: string
  threshold_pct: number
  active: boolean
  last_price?: number | null
  created_at: string
}

export interface FuelAlert {
  watch_id: string
  user_id: string
  station_id: string
  station_name?: string | null
  state: string
  fuel_type: string
  previous_price?: number | null
  current_price: number
  change_pct: number
  direction: 'up' | 'down'
  threshold_pct: number
  notified: boolean
  created_at: string
}

import { apiFetch } from '@shared/utils'

const BASE = '/api/v1/fuel-watchlist'

export function listWatches(userId = 'default-user') {
  return apiFetch<FuelWatch[]>(`${BASE}?user_id=${encodeURIComponent(userId)}`)
}

export function createWatch(payload: {
  user_id?: string
  station_id: string
  station_name?: string
  state: string
  fuel_type: string
  threshold_pct: number
}) {
  return apiFetch<FuelWatch>(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function patchWatch(watchId: string, payload: Partial<FuelWatch>) {
  return apiFetch<FuelWatch>(`${BASE}/${watchId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function deleteWatch(watchId: string) {
  return apiFetch<{ deleted: string }>(`${BASE}/${watchId}`, { method: 'DELETE' })
}

export function checkAlerts(userId = 'default-user') {
  return apiFetch<FuelAlert[]>(`${BASE}/check-alerts?user_id=${encodeURIComponent(userId)}`, {
    method: 'POST',
  })
}

export function listNotifications(userId = 'default-user') {
  return apiFetch<FuelAlert[]>(`${BASE}/notifications?user_id=${encodeURIComponent(userId)}`)
}
