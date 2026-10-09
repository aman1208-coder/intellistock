import { FormEvent, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { login, register } from './api';
import './polish.css';

type Mode = 'login' | 'register';
const POINTS = ['Realtime stock health', 'Warehouse-aware demand planning', 'Safe allocation and queue monitoring'];

export default function Login({ onDone }: { onDone: (username: string) => void }) {
  const [mode, setMode] = useState<Mode>('login');
  const [form, setForm] = useState({ username: '', email: '', password: '' });
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
      if (mode === 'register') await register(form.email, form.username, form.password);
      await login(form.username.trim(), form.password);
      onDone(form.username.trim());
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
            <span className="lg-orbit" aria-hidden="true"><i /></span>
            <div><small>WAREHOUSE INTELLIGENCE</small><h1>IntelliStock</h1></div>
          </div>
          <motion.p {...rise(0)}>Track fulfillment, replenishment risk and inventory flow from a single control room.</motion.p>
          <ul>{POINTS.map((t, i) => <motion.li key={t} {...rise(i + 1)}>{t}</motion.li>)}</ul>
        </div>

        <motion.form className="lg-form" onSubmit={submit} animate={calm || !shake ? {} : { x: [0, -8, 8, -5, 5, 0] }} transition={{ duration: 0.4 }} key={`f${shake}`}>
          <small>SECURE ACCESS</small>
          <h2>{mode === 'login' ? 'Welcome back' : 'Create account'}</h2>
          <div className="lg-tabs" role="tablist">
            {(['login', 'register'] as Mode[]).map((m) => (
              <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setError(''); }}>
                {mode === m && <motion.span layoutId="lg-tab" className="lg-pill" transition={{ type: 'spring', stiffness: 400, damping: 32 }} />}
                <span>{m === 'login' ? 'Sign in' : 'Register'}</span>
              </button>
            ))}
          </div>
          <input aria-label="Username or email" placeholder={mode === 'login' ? 'Username or email' : 'Username'} value={form.username} onChange={set('username')} autoComplete="username" required />
          {mode === 'register' && <input aria-label="Email" type="email" placeholder="Email" value={form.email} onChange={set('email')} autoComplete="email" required />}
          <input aria-label="Password" type="password" placeholder="Password" value={form.password} onChange={set('password')} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required />
          {error && <p className="lg-error" role="alert">{error}</p>}
          <motion.button className="lg-primary" disabled={busy} whileHover={calm ? undefined : { scale: 1.02 }} whileTap={calm ? undefined : { scale: 0.98 }}>
            {busy ? 'Please wait' : mode === 'login' ? 'Sign in' : 'Create account'}
          </motion.button>
        </motion.form>
      </motion.section>
    </main>
  );
}
