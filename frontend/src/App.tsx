import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { PetrolPriceMapScreen } from '@features/fuelPrice';
import { FuelServiceScreen } from '@features/fuelService';
import { OwnershipAdvisorScreen } from '@features/ownershipAdvisor';
import { EngineeringHelperScreen } from '@features/engineeringHelper';
import WatchlistScreen from '@features/fuelWatchlist';
import { getVehicleHealth, getEngineeringHelper } from '@features/vehicles';
import { useState } from 'react';

const NavLink = ({ to, children }: { to: string; children: React.ReactNode }) => {
  const location = useLocation();
  const active = location.pathname === to;
  return (
    <Link
      to={to}
      style={{
        padding: '8px 16px',
        borderRadius: 6,
        background: active ? '#1e3a5f' : 'transparent',
        border: '1px solid',
        borderColor: active ? '#3b82f6' : '#333',
        color: active ? '#fff' : '#e5e7eb',
        textDecoration: 'none',
        fontWeight: active ? 600 : 500,
        transition: 'all 0.2s',
      }}
    >
      {children}
    </Link>
  );
};

function Header() {
  return (
    <header style={{ padding: '16px 24', borderBottom: '1px solid #333', background: '#0d0d0d' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ fontSize: 24 }}>🧠</div>
          <span style={{ fontSize: 20, fontWeight: 700 }}>AutoBrain</span>
        </div>
        <nav style={{ display: 'flex', gap: 8 }}>
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/fuel-prices">Servo Spy</NavLink>
          <NavLink to="/watchlist">Watchlist</NavLink>
          <NavLink to="/engineering-helper">VASS</NavLink>
          <NavLink to="/fuel-service">Fuel & Service</NavLink>
          <NavLink to="/ownership-advisor">Ownership Advisor</NavLink>
        </nav>
      </div>
    </header>
  );
}

function Dashboard() {
  const [result, setResult] = useState<string>('');
  const [helper, setHelper] = useState<string>('');
  const [loading, setLoading] = useState(false);

  async function check() {
    setLoading(true);
    try {
      const h = await getVehicleHealth('VIN1234567890');
      setResult(`${h.vehicle_id}: ${h.overall_score} (${h.overall_status})`);
      if (h.engineering_helper) {
        const eh = h.engineering_helper;
        setHelper(`${eh.primary_title} (${eh.primary_severity}): ${eh.primary_message}`);
      } else {
        setHelper('');
      }
      try {
        const eh = await getEngineeringHelper('VIN1234567890', {
          engine_light_on: false,
          fault_codes: [],
          rego_valid: true,
          service_interval_km: 10000,
          ownership_status: 'registered',
        });
        setHelper(`${eh.primary_title} (${eh.primary_severity}): ${eh.primary_message}`);
      } catch (e) {
        setHelper(String(e));
      }
    } catch (e) {
      setResult(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Vehicle Health</h1>
      <button onClick={check} disabled={loading} style={{ padding: '10px 20px', marginBottom: 16 }}>
        {loading ? 'Loading…' : 'Check vehicle health'}
      </button>
      <p>{result}</p>
      <h2>VASS Engineering Helper</h2>
      <p>{helper}</p>
    </main>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div style={{ minHeight: '100vh', background: '#050505', color: '#e5e7eb' }}>
        <Header />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/fuel-prices" element={<PetrolPriceMapScreen />} />
          <Route path="/watchlist" element={<WatchlistScreen />} />
          <Route path="/engineering-helper" element={<EngineeringHelperScreen />} />
          <Route path="/ownership-advisor" element={<OwnershipAdvisorScreen />} />
          <Route path="/fuel-service" element={<FuelServiceScreen />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;