export type VehicleId = string

export interface ComponentHealth {
  name: string
  score: number
  status: 'EXCELLENT' | 'GOOD' | 'FAIR' | 'POOR' | 'CRITICAL'
  details?: string
}

export interface EngineeringHelperSummary {
  primary_state: string
  primary_severity: string
  primary_title: string
  primary_message: string
  ai_explanation?: string
  used_fallback: boolean
}

export interface VehicleHealth {
  vehicle_id: VehicleId
  overall_score: number
  overall_status: ComponentHealth['status']
  components: ComponentHealth[]
  last_updated: string
  mileage?: number
  engineering_helper?: EngineeringHelperSummary
}

export interface Vehicle {
  id: VehicleId
  make?: string
  model?: string
  year?: number
}

export interface Modification {
  id: string
  vehicle_id: VehicleId
  type: string
  description: string
  date: string
}

export interface Booking {
  id: string
  vehicle_id: VehicleId
  service_type: string
  date: string
  status: 'pending' | 'confirmed' | 'completed' | 'cancelled'
}

export interface UserProfile {
  id: string
  name: string
  email: string
}
