export type FuelState = 'WA' | 'QLD' | 'NSW' | 'ACT' | 'VIC';

export type FeedStatus = 'ok' | 'down' | 'pending';

export interface FeedHealth {
  state: string;
  feed: string;
  status: FeedStatus;
  last_success: string | null;
  last_error: string | null;
}

export interface Station {
  id: string;
  name: string;
  state: string;
  suburb?: string;
  price_cpl?: number;
  fuel_type?: string;
  updated_at?: string;
  freshness_minutes?: number;
  lat?: number;
  lng?: number;
}

export interface FuelPriceResponse {
  state: string;
  available: boolean;
  message?: string;
  stations: Station[];
  feed_status?: FeedHealth;
}

export interface FeedHealthResponse {
  feeds: FeedHealth[];
}

const STATES: FuelState[] = ['WA', 'QLD', 'NSW', 'ACT', 'VIC'];

const STATE_LABELS: Record<FuelState, string> = {
  WA: 'Western Australia',
  QLD: 'Queensland',
  NSW: 'New South Wales',
  ACT: 'Australian Capital Territory',
  VIC: 'Victoria',
};

export function getStates(): FuelState[] {
  return STATES;
}

export function getStateLabel(state: FuelState): string {
  return STATE_LABELS[state];
}

export function getAvailableStates(): FuelState[] {
  return ['WA', 'QLD'];
}

export function isStateAvailable(state: FuelState): boolean {
  return ['WA', 'QLD'].includes(state);
}

import { apiFetch } from '@shared/utils';

export async function fetchFuelPrices(state: FuelState): Promise<FuelPriceResponse> {
  return apiFetch<FuelPriceResponse>(`/api/v1/fuel-price/${state}`);
}

export async function fetchFeedHealth(): Promise<FeedHealthResponse> {
  return apiFetch<FeedHealthResponse>(`/api/v1/fuel-price/feeds/health`);
}