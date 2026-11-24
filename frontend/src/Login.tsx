import { FormEvent, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { login, type UserRole } from './api';
import BrandMark from './components/BrandMark';
import './polish.css';

const POINTS = ['Realtime stock health', 'Warehouse-aware demand planning', 'Safe allocation and queue monitoring'];

export default function Login({ onDone }: { onDone: (username: string, role: UserRole) => void }) {
  const [form, setForm] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [shake, setShake] = useState(0);
  const calm = Boolean(useReducedMotion());
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const session = await login(form.username.trim(), form.password);
      onDone(form.username.trim(), session.role);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      setError(msg && msg !== 'Failed to fetch' ? msg : 'Cannot reach the API. Start the backend on port 8000, or continue with demo data.');
      setShake((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }

  const rise = (i: number) => (calm ? {} : { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { delay: 0.25 + i * 0.08, duration: 0.45 } });

  return (
    <main className="lg-page">
      <motion.section
        className="lg-card"
        initial={calm ? false : { opacity: 0, y: 30, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: 'spring', stiffness: 120, damping: 18 }}
      >
        <div className="lg-pitch">
          <div className="lg-brand">
            <BrandMark size={44} />
            <div><small>WAREHOUSE INTELLIGENCE</small><h1>IntelliStock</h1></div>
          </div>
          <motion.p {...rise(0)}>Track fulfillment, replenishment risk and inventory flow from a single control room.</motion.p>
          <ul>{POINTS.map((t, i) => <motion.li key={t} {...rise(i + 1)}>{t}</motion.li>)}</ul>
        </div>

        <motion.form className="lg-form" onSubmit={submit} animate={calm || !shake ? {} : { x: [0, -8, 8, -5, 5, 0] }} transition={{ duration: 0.4 }} key={`f${shake}`}>
          <small>SECURE ACCESS</small>
          <h2>Welcome back</h2>
          <input aria-label="Username or email" placeholder="Username or email" value={form.username} onChange={set('username')} autoComplete="username" required />
          <input aria-label="Password" type="password" placeholder="Password" value={form.password} onChange={set('password')} autoComplete="current-password" required />
          {error && <p className="lg-error" role="alert">{error}</p>}
          <motion.button className="lg-primary" disabled={busy} whileHover={calm ? undefined : { scale: 1.02 }} whileTap={calm ? undefined : { scale: 0.98 }}>
            {busy ? 'Please wait' : 'Sign in'}
          </motion.button>
          <p className="lg-account-note">New accounts are created by an administrator. Contact your administrator to request access.</p>
        </motion.form>
      </motion.section>
    </main>
  );
}
