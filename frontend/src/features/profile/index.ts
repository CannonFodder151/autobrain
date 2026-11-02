import { apiFetch } from '@shared/utils'
import type { UserProfile } from '@shared/types'

export function getProfile() {
  return apiFetch<UserProfile>('/api/v1/profile')
}