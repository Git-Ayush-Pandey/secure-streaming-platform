import React, { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { setDashboardToken } from '../api/dashboardToken';
import { useApp } from '../context/AppContext';

/**
 * Shown instead of the dashboard when no valid bearer token is stored.
 * The backend prints a bootstrap URL on startup under
 * "=== Dashboard access ===" — visiting that URL is the easiest path
 * (the token is captured automatically from the ?token= query param).
 * This screen is the manual fallback.
 */
export default function AuthGate() {
  const { dispatch, refreshServerInfo } = useApp();
  const [value, setValue]   = useState('');
  const [error, setError]   = useState('');
  const [loading, setLoading] = useState(false);

  async function connect() {
    const trimmed = value.trim();
    if (!trimmed) {
      setError('Paste the token from the server console first.');
      return;
    }
    setError('');
    setLoading(true);

    // 1. Persist the token to localStorage.
    setDashboardToken(trimmed);

    // 2. Immediately fire the server-info fetch with the new token.
    //    fetchServerInfo reads getDashboardToken() at call time (not from
    //    a closure) so it will pick up the token we just saved.
    try {
      await refreshServerInfo();
      // If the fetch succeeded, AppContext dispatches CLEAR_NEEDS_AUTH
      // and AppShell will unmount this component. Nothing more to do here.
    } catch (_) {
      // fetchServerInfo swallows errors internally and dispatches the
      // right state; this catch is just a safety net.
      setError('Could not reach the server. Check that the backend is running.');
      setLoading(false);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    connect();
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') connect();
  }

  return (
    <div className="auth-gate">
      <div className="auth-gate-card">
        <ShieldAlert size={28} color="var(--accent-red)" />
        <h2>Dashboard authentication required</h2>
        <p>
          The server prints an access token on startup under{' '}
          <strong>=== Dashboard access ===</strong>. Paste the token below,
          or open the full bootstrap URL the server printed — that stores
          the token automatically.
        </p>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Paste dashboard token here"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            autoFocus
            spellCheck={false}
            autoComplete="off"
          />
          <button
            type="submit"
            onClick={connect}
            disabled={loading || !value.trim()}
          >
            {loading ? 'Connecting…' : 'Connect'}
          </button>
        </form>

        {error && (
          <p style={{ color: 'var(--accent-red)', marginTop: 8, fontSize: 12 }}>
            {error}
          </p>
        )}

        <p className="auth-gate-hint">
          The token is also stored at{' '}
          <code>server/backend/data/config/.dashboard_token</code> on the
          machine running the backend.
        </p>
      </div>
    </div>
  );
}
