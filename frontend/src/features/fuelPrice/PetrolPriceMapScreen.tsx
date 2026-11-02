import { useState, useEffect, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import {
  fetchFuelPrices,
  fetchFeedHealth,
  getStates,
  getStateLabel,
  isStateAvailable,
  type FuelState,
  type Station,
  type FeedHealth,
  type FuelPriceResponse,
} from './api';

const STATE_ORDER: FuelState[] = ['WA', 'QLD', 'NSW', 'ACT', 'VIC'];

function formatFreshness(minutes: number | undefined): string {
  if (minutes === undefined || minutes === null) return 'Unknown';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function FreshnessBadge({ minutes }: { minutes: number | undefined }) {
  const text = formatFreshness(minutes);
  let color = '#4ade80';
  if (minutes === undefined) color = '#fbbf24';
  else if (minutes > 60) color = '#fbbf24';
  else if (minutes > 180) color = '#f87171';
  return <span style={{ color, fontSize: 12, fontWeight: 600 }}>{text}</span>;
}

function FeedStatusIndicator({ health }: { health: FeedHealth }) {
  const colors: Record<string, string> = {
    ok: '#4ade80',
    down: '#f87171',
    pending: '#fbbf24',
  };
  const labels: Record<string, string> = {
    ok: 'Live',
    down: 'Down',
    pending: 'Pending',
  };
  const color = colors[health.status] || '#888';
  const label = labels[health.status] || health.status;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 8px',
        borderRadius: 12,
        background: `${color}20`,
        color,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: color,
        }}
      />
      {label} — {health.feed}
    </span>
  );
}

function StationList({ stations }: { stations: Station[] }) {
  if (!stations.length) return <p style={{ color: '#888', padding: 16 }}>No stations found.</p>;
  return (
    <div style={{ maxHeight: 400, overflow: 'auto' }}>
      {stations.map((s) => (
        <div
          key={s.id}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 16px',
            borderBottom: '1px solid #333',
          }}
        >
          <div>
            <div style={{ fontWeight: 600 }}>{s.name}</div>
            <div style={{ fontSize: 12, color: '#888' }}>
              {s.suburb}, {s.state} • {s.fuel_type}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#4ade80' }}>
              {s.price_cpl?.toFixed(1)}¢/L
            </div>
            <FreshnessBadge minutes={s.freshness_minutes} />
          </div>
        </div>
      ))}
    </div>
  );
}

function UnavailableMessage({ state, message }: { state: FuelState; message: string }) {
  return (
    <div
      style={{
        padding: 32,
        textAlign: 'center',
        background: '#1a1a1a',
        borderRadius: 12,
        border: '1px solid #333',
      }}
    >
      <div style={{ fontSize: 48, marginBottom: 16 }}>⛽</div>
      <h3 style={{ margin: '0 0 8px', color: '#fbbf24' }}>Fuel prices unavailable for {state}</h3>
      <p style={{ margin: 0, color: '#aaa' }}>{message}</p>
    </div>
  );
}

function MapPlaceholder({ state }: { state: FuelState }) {
  return (
    <div
      style={{
        height: 300,
        background: '#111',
        border: '1px solid #333',
        borderRadius: 12,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#666',
        position: 'relative',
      }}
    >
      <div style={{ fontSize: 48, marginBottom: 8 }}>🗺️</div>
      <div style={{ fontWeight: 600 }}>Map view for {state}</div>
      <div style={{ fontSize: 12, marginTop: 8 }}>Leaflet / MapLibre integration pending</div>
      <div style={{ fontSize: 11, marginTop: 4, color: '#555' }}>
        Stations would render as markers with price popups here.
      </div>
    </div>
  );
}

function MapView({ stations }: { stations: Station[] }) {
  const validStations = stations.filter(
    (s): s is Station & { lat: number; lng: number } =>
      typeof s.lat === 'number' && typeof s.lng === 'number'
  );

  if (!validStations.length) {
    return <MapPlaceholder state="WA" />;
  }

  const centerLat = validStations.reduce((sum, s) => sum + s.lat!, 0) / validStations.length;
  const centerLng = validStations.reduce((sum, s) => sum + s.lng!, 0) / validStations.length;

  return (
    <div style={{ height: 300, borderRadius: 12, overflow: 'hidden', border: '1px solid #333' }}>
      <MapContainer
        center={[centerLat, centerLng]}
        zoom={8}
        scrollWheelZoom={true}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {validStations.map((station) => (
          <Marker key={station.id} position={[station.lat!, station.lng!]}>
            <Popup>
              <div style={{ minWidth: 180 }}>
                <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>{station.name}</h4>
                <p style={{ margin: '0 0 4px', fontSize: 12, color: '#666' }}>
                  {station.suburb}, {station.state}
                </p>
                <p style={{ margin: '0 0 4px', fontSize: 12 }}>
                  <strong>{station.fuel_type}</strong>: {station.price_cpl?.toFixed(1)}¢/L
                </p>
                <p style={{ margin: 0, fontSize: 11, color: '#888' }}>
                  Updated: {station.freshness_minutes !== undefined ? `${station.freshness_minutes}m ago` : 'Unknown'}
                </p>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

export default function PetrolPriceMapScreen() {
  const [state, setState] = useState<FuelState>('WA');
  const [data, setData] = useState<FuelPriceResponse | null>(null);
  const [feedHealth, setFeedHealth] = useState<FeedHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [priceRes, healthRes] = await Promise.all([
        fetchFuelPrices(state),
        fetchFeedHealth(),
      ]);
      setData(priceRes);
      setFeedHealth(healthRes.feeds);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [state]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const currentFeed = feedHealth.find((f) => f.state === state);

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      <header style={{ marginBottom: 24 }}>
        <h1 style={{ margin: '0 0 8px', fontSize: 28 }}>Servo Spy — Fuel Price Watch</h1>
        <p style={{ margin: 0, color: '#888' }}>
          Live fuel prices from official and partner feeds.{' '}
          <strong>WA</strong> (official) & <strong>QLD</strong> (partner) are live.{' '}
          NSW/ACT/VIC pending partner-feed keys.
        </p>
      </header>

      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 24,
          flexWrap: 'wrap',
        }}
        role="tablist"
        aria-label="Select state"
      >
        {STATE_ORDER.map((s) => {
          const available = isStateAvailable(s);
          const isActive = state === s;
          const health = feedHealth.find((f) => f.state === s);
          return (
            <button
              key={s}
              role="tab"
              aria-selected={isActive}
              onClick={() => setState(s)}
              disabled={!available && !isActive}
              style={{
                padding: '10px 16px',
                borderRadius: 8,
                border: '1px solid',
                background: isActive ? '#1e3a5f' : '#1a1a1a',
                borderColor: isActive ? '#3b82f6' : '#333',
                color: isActive ? '#fff' : available ? '#e5e7eb' : '#666',
                fontWeight: isActive ? 700 : 500,
                cursor: available || isActive ? 'pointer' : 'not-allowed',
                opacity: available || isActive ? 1 : 0.6,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 4,
                minWidth: 80,
              }}
            >
              {s}
              {health && (
                <span
                  style={{
                    fontSize: 10,
                    padding: '2px 6px',
                    borderRadius: 4,
                    background:
                      health.status === 'ok'
                        ? '#065f46'
                        : health.status === 'down'
                        ? '#7f1d1d'
                        : '#78350f',
                    color:
                      health.status === 'ok'
                        ? '#a7f3d0'
                        : health.status === 'down'
                        ? '#fca5a5'
                        : '#fde68a',
                  }}
                >
                  {health.status === 'ok' ? 'Live' : health.status === 'down' ? 'Down' : 'Pending'}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {loading && (
        <div style={{ padding: 48, textAlign: 'center', color: '#888' }}>Loading…</div>
      )}

      {error && (
        <div style={{ padding: 24, background: '#7f1d1d', borderRadius: 8, color: '#fca5a5' }}>
          Error: {error}
        </div>
      )}

      {data && !loading && (
        <>
          {currentFeed && (
            <div style={{ marginBottom: 16 }}>
              <FeedStatusIndicator health={currentFeed} />
            </div>
          )}

          {data.available ? (
            <>
              <MapView stations={data.stations} />
              <div style={{ marginTop: 24 }}>
                <h3 style={{ margin: '0 0 12px' }}>Stations</h3>
                <StationList stations={data.stations} />
              </div>
            </>
          ) : (
            <UnavailableMessage state={state} message={data.message || 'No data available'} />
          )}
        </>
      )}
    </div>
  );
}