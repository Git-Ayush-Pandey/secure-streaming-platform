import React, { useState } from 'react';
import { ShieldAlert } from 'lucide-react';
import { setDashboardToken } from '../api/dashboardToken';
import { useApp } from '../context/AppContext';

/**
 * F1: shown instead of the dashboard when no valid bearer token is
 * stored. The backend prints a one-time bootstrap URL on startup
 * (console output: "=== Dashboard access ===") that contains the token
 * as a `?token=` query parameter — visiting that link is the normal
 * path and never hits this screen. This is a fallback for when the
 * link wasn't used (token cleared, different browser, token rotated).
 */
export default function AuthGate() {
    const { refreshServerInfo } = useApp();
    const [value, setValue] = useState('');

    function submit(e) {
        e.preventDefault();
        const trimmed = value.trim();
        if (!trimmed) return;
        setDashboardToken(trimmed);
        refreshServerInfo();
    }

    return (
        <div className="auth-gate">
            <div className="auth-gate-card">
                <ShieldAlert size={28} color="var(--accent-red)" />
                <h2>Dashboard authentication required</h2>
                <p>
                    This dashboard requires the access token printed in the server's
                    console on startup, under <strong>=== Dashboard access ===</strong>.
                    Paste the token below, or open the full bootstrap link the server
                    printed (it stores the token automatically).
                </p>
                <form onSubmit={submit}>
                    <input
                        type="text"
                        placeholder="Paste dashboard token"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        autoFocus
                    />
                    <button type="submit">Connect</button>
                </form>
                <p className="auth-gate-hint">
                    The token is also stored at{' '}
                    <code>server/backend/data/config/.dashboard_token</code> on the
                    machine running the backend.
                </p>
            </div>
        </div>
    );
}