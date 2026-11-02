import { apiFetch } from '@shared/utils'

export interface RegoResult {
  rego: string
  state: string
  vin?: string | null
  body?: string | null
  colour?: string | null
  status: string
  make?: string | null
  model?: string | null
  year?: number | null
  errors?: string[]
}

export function lookupRego(rego: string, state = 'NSW') {
  return apiFetch<RegoResult>(`/api/v1/rego/lookup?rego=${encodeURIComponent(rego)}&state=${encodeURIComponent(state)}`)
}