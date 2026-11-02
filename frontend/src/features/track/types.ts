import type { VehicleId } from '@shared/types'

export interface TrackCarProfile {
  id: string
  baseVehicleId: VehicleId
  trackOnly: boolean
  class?: string
  weight?: number
  power?: number
  tyreSpec?: string
}

export interface TrackDaySession {
  id: string
  carId: string
  trackId: string
  date: string
  weather?: string
  driverId: string
  notes?: string
}

export interface LapSector {
  number: number
  timeMs: number
}

export interface TyrePressure {
  corner: 'FL' | 'FR' | 'RL' | 'RR'
  cold?: number
  hot?: number
}

export interface BrakeTemp {
  corner: 'FL' | 'FR' | 'RL' | 'RR'
  tempC: number
}

export interface Lap {
  id: string
  sessionId: string
  number: number
  timeMs: number
  sectors: LapSector[]
  fuelUsed?: number
  tyrePressures: TyrePressure[]
  brakeTemps: BrakeTemp[]
}

export interface PrepChecklistItem {
  key: string
  done: boolean
  note?: string
}

export interface PrepChecklist {
  id: string
  sessionId: string
  items: PrepChecklistItem[]
  completedAt?: string
}

export interface ServiceEvent {
  id: string
  carId: string
  kind: 'oil' | 'brake_fluid' | 'coolant' | 'tyres' | 'other'
  mileageOrHours?: number
  trackHours: number
  dueAt?: string
  done: boolean
}

export interface DriverStat {
  driverId: string
  trackId: string
  bestLapMs: number
  avgLapMs: number
  consistency: number
  sessionsCount: number
}
