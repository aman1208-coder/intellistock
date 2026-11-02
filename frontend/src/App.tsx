import { useEffect, useState } from 'react';
import Dashboard from './Dashboard';
import Login from './Login';
import SolarSystem from './SolarSystem';
import { clearToken, getToken } from './api';
import type { UserRole } from './api';

const USERNAME_STORAGE_KEY = 'intellistock_username';
const ROLE_STORAGE_KEY = 'intellistock_role';

function readStoredRole(): UserRole {
  const role = localStorage.getItem(ROLE_STORAGE_KEY);
  return role === 'ADMIN' || role === 'WAREHOUSE_MANAGER' ? role : 'STAFF';
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getToken()));
  const [username, setUsername] = useState(() => localStorage.getItem(USERNAME_STORAGE_KEY) ?? 'Signed-in user');
  const [role, setRole] = useState<UserRole>(readStoredRole);

  useEffect(() => {
    const handleLogout = () => {
      setIsAuthenticated(false);
      setUsername('');
      localStorage.removeItem(USERNAME_STORAGE_KEY);
      localStorage.removeItem(ROLE_STORAGE_KEY);
      setRole('STAFF');
    };

    window.addEventListener('intellistock:logout', handleLogout);
    return () => window.removeEventListener('intellistock:logout', handleLogout);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    const landingSection = role === 'ADMIN' ? 'banker' : role === 'WAREHOUSE_MANAGER' ? 'forecast' : 'overview';
    window.location.hash = landingSection;
  }, [isAuthenticated, role]);

  const handleLogout = () => {
    clearToken();
    localStorage.removeItem(USERNAME_STORAGE_KEY);
    localStorage.removeItem(ROLE_STORAGE_KEY);
    setIsAuthenticated(false);
    setUsername('');
    setRole('STAFF');
    window.dispatchEvent(new Event('intellistock:logout'));
  };

  return (
    <div className="app-shell">
      <SolarSystem />
      <div className="app-layer">
        {isAuthenticated ? (
          <Dashboard username={username || 'Signed-in user'} role={role} onLogout={handleLogout} />
        ) : (
          <Login
            onDone={(signedInUsername, signedInRole) => {
              localStorage.setItem(USERNAME_STORAGE_KEY, signedInUsername);
              localStorage.setItem(ROLE_STORAGE_KEY, signedInRole);
              setUsername(signedInUsername);
              setRole(signedInRole);
              setIsAuthenticated(true);
            }}
          />
        )}
      </div>
    </div>
  );
}
