import { apiFetch, apiBase } from '@shared/utils'
import type {
  FuelFillUp,
  ServiceRecord,
  EconomyResponse,
  SpendingResponse,
} from './types'

const BASE = '/api/v1/fuel-service'

export function addFuelFillUp(payload: Omit<FuelFillUp, 'id' | 'totalCost'>) {
  return apiFetch<FuelFillUp>(`${BASE}/fuel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listFuelFillUps(vehicleId: string) {
  return apiFetch<FuelFillUp[]>(`${BASE}/fuel?vehicleId=${encodeURIComponent(vehicleId)}`)
}

export function addServiceRecord(payload: Omit<ServiceRecord, 'id'>) {
  return apiFetch<ServiceRecord>(`${BASE}/service`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listServiceRecords(vehicleId: string) {
  return apiFetch<ServiceRecord[]>(`${BASE}/service?vehicleId=${encodeURIComponent(vehicleId)}`)
}

export function getEconomy(vehicleId: string) {
  return apiFetch<EconomyResponse>(`${BASE}/economy?vehicleId=${encodeURIComponent(vehicleId)}`)
}

export function getSpending(vehicleId: string) {
  return apiFetch<SpendingResponse>(`${BASE}/spending?vehicleId=${encodeURIComponent(vehicleId)}`)
}

export function getTaxExportUrl(vehicleId: string, businessUsePct: number) {
  return `${apiBase}${BASE}/tax-export?vehicleId=${encodeURIComponent(vehicleId)}&businessUsePct=${businessUsePct}`
}
