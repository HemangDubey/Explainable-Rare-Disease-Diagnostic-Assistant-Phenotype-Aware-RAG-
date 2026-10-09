import React, { useState } from 'react';
import { loginUser, registerUser, getSession } from '../api/client';

// Sign-in / registration card in the existing design system. `notice` is shown above the form (e.g. the session-expired message).
export default function AuthPanel({ onAuthenticated, notice = null }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [problems, setProblems] = useState([]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setProblems([]);
    try {
      if (mode === 'register') {
        await registerUser({ email, password, display_name: name || undefined });
      }
      await loginUser({ email, password });
      onAuthenticated(getSession());
      setPassword('');
    } catch (err) {
      setError(err.httpStatus === 429 ? 'Too many attempts. Please wait a moment and try again.' : err.message || 'Something went wrong.');
      setProblems(err.problems || []);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-md w-full mx-auto bg-surface-container-lowest rounded-2xl p-space-xl shadow-sm border border-outline-variant/30 flex flex-col gap-space-md">
      <div className="flex items-center gap-space-xs">
        <span className="material-symbols-outlined text-secondary text-[28px]">lock</span>
        <div>
          <h2 className="font-title-lg text-primary font-bold">{mode === 'login' ? 'Sign in' : 'Create an account'}</h2>
          <p className="text-label-sm text-on-surface-variant">Your cases, drafts, scenarios and reports are private to your account.</p>
        </div>
      </div>

      {notice && <div className="p-space-sm rounded-xl bg-tertiary-fixed text-on-tertiary-fixed text-body-sm font-semibold">{notice}</div>}

      <form onSubmit={submit} className="flex flex-col gap-space-sm" noValidate>
        {mode === 'register' && (
          <label className="flex flex-col gap-1 text-label-md text-on-surface-variant">
            Display name (optional)
            <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} autoComplete="name"
              className="p-space-sm rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary" />
          </label>
        )}
        <label className="flex flex-col gap-1 text-label-md text-on-surface-variant">
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required
            className="p-space-sm rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary" />
        </label>
        <label className="flex flex-col gap-1 text-label-md text-on-surface-variant">
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required maxLength={128}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            className="p-space-sm rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary" />
          {mode === 'register' && <span className="text-[11px]">At least 12 characters; avoid common passwords.</span>}
        </label>

        {error && (
          <div role="alert" className="p-space-sm rounded-xl bg-error-container text-on-error-container text-body-sm">
            {error}
            {problems.length > 0 && <ul className="list-disc list-inside mt-1">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>}
          </div>
        )}

        <button type="submit" disabled={busy || !email || !password}
          className="py-space-sm rounded-xl bg-primary text-on-primary font-label-lg font-bold hover:bg-primary/90 transition-all shadow-md disabled:opacity-50 flex items-center justify-center gap-space-xs">
          <span className="material-symbols-outlined text-[20px]">{busy ? 'progress_activity' : 'login'}</span>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account and sign in'}
        </button>
      </form>

      <button type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null); setProblems([]); }}
        className="text-label-md text-secondary font-bold hover:underline self-start">
        {mode === 'login' ? 'New here? Create an account' : 'Already registered? Sign in'}
      </button>
      <p className="text-[11px] text-on-surface-variant">
        Research prototype. Do not enter real patient data unless your organisation has approved this deployment; submitted text may be processed by an external language-model service.
      </p>
    </div>
  );
}
