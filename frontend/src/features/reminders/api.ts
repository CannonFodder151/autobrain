import { apiFetch } from '@shared/utils'

export interface Reminder {
  id: string
  vehicleId: string
  kind: string
  dueDate: string
  message?: string
  createdAt: string
}

export function createReminder(payload: Omit<Reminder, 'id' | 'createdAt'>) {
  return apiFetch<Reminder>('/api/v1/reminders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function listReminders(vehicleId: string) {
  return apiFetch<Reminder[]>(`/api/v1/reminders?vehicleId=${encodeURIComponent(vehicleId)}`)
}