import { getDashboardToken, clearDashboardToken } from './dashboardToken';

const BASE = import.meta.env.VITE_API_URL;

export class DashboardAuthError extends Error {
  constructor(message) {
    super(message);
    this.name = 'DashboardAuthError';
  }
}

export async function apiFetch(path, options = {}) {
  const token = getDashboardToken();

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  // F1: attach the dashboard bearer token to every admin API call.
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Stored token is missing/stale (e.g. rotated on the backend) — drop
    // it so the UI falls back to the "needs bootstrap link" state rather
    // than retrying forever with a dead token.
    clearDashboardToken();
    throw new DashboardAuthError(`API ${path} requires dashboard authentication`);
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

export const WS_BASE = import.meta.env.VITE_WS_URL;