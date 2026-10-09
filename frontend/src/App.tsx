import { useEffect, useState } from 'react';
import Dashboard from './Dashboard';
import Login from './Login';
import SolarSystem from './SolarSystem';
import { clearToken, getToken } from './api';

const USERNAME_STORAGE_KEY = 'intellistock_username';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getToken()));
  const [username, setUsername] = useState(() => localStorage.getItem(USERNAME_STORAGE_KEY) ?? 'Signed-in user');

  useEffect(() => {
    const handleLogout = () => {
      setIsAuthenticated(false);
      setUsername('');
      localStorage.removeItem(USERNAME_STORAGE_KEY);
    };

    window.addEventListener('intellistock:logout', handleLogout);
    return () => window.removeEventListener('intellistock:logout', handleLogout);
  }, []);

  const handleLogout = () => {
    clearToken();
    localStorage.removeItem(USERNAME_STORAGE_KEY);
    setIsAuthenticated(false);
    setUsername('');
    window.dispatchEvent(new Event('intellistock:logout'));
  };

  return (
    <div className="app-shell">
      <SolarSystem />
      <div className="app-layer">
        {isAuthenticated ? (
          <Dashboard username={username || 'Signed-in user'} onLogout={handleLogout} />
        ) : (
          <Login
            onDone={(signedInUsername) => {
              localStorage.setItem(USERNAME_STORAGE_KEY, signedInUsername);
              setUsername(signedInUsername);
              setIsAuthenticated(true);
            }}
          />
        )}
      </div>
    </div>
  );
}
