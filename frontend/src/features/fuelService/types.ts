export interface FuelFillUp {
  id: string
  vehicleId: string
  date: string
  litres: number
  pricePerLitre: number
  odometer: number
  station?: string | null
  fuelType?: string | null
  totalCost: number
}

export interface ServiceRecord {
  id: string
  vehicleId: string
  date: string
  mileage: number
  cost: number
  items: string[]
}

export interface EconomyReading {
  fillUpId: string
  date: string
  km: number
  litres: number
  lPer100km: number | null
}

export interface EconomyResponse {
  vehicleId: string
  readings: EconomyReading[]
}

export interface SpendingBucket {
  month: string
  total: number
}

export interface SpendingResponse {
  vehicleId: string
  monthly: SpendingBucket[]
}