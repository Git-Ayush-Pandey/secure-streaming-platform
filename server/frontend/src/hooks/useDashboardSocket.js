import { useEffect, useRef } from 'react';
import { WS_BASE } from '../api/api';
import { CONFIG } from '../config';
import { getDashboardToken, clearDashboardToken } from '../api/dashboardToken';

// Matches the close code the backend sends from dashboard_ws() in main.py
// when dashboard_ws_token_valid() rejects the handshake (see
// services/dashboard_auth.py — F1).
const WS_CLOSE_AUTH_FAILED = 4401;

/**
 * Connects to /ws/dashboard and calls onEvent(event, data) for each message.
 * Auto-reconnects every {CONFIG.WS_RECONNECT_INTERVAL} ms on disconnect.
 *
 * F1: the bearer token used by the REST API is appended as a `?token=`
 * query parameter, since browsers cannot set custom headers on a
 * WebSocket upgrade request. This is the same mechanism the backend's
 * dashboard_ws_token_valid() expects (see services/dashboard_auth.py).
 *
 * onAuthError(optional): called once if the server closes the socket
 * with the auth-failure code, so the UI can show a "needs token" state
 * instead of silently retrying with a token the server has already
 * rejected.
 */
export function useDashboardSocket(onEvent, onAuthError) {
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const onEventRef = useRef(onEvent);
  const onAuthErrorRef = useRef(onAuthError);

  // Keep refs current without re-running effect
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);
  useEffect(() => { onAuthErrorRef.current = onAuthError; }, [onAuthError]);

  useEffect(() => {
    let destroyed = false;

    function connect() {
      if (destroyed) return;

      const token = getDashboardToken();
      if (!token) {
        // No point opening a socket the server will immediately reject;
        // wait for a token to show up (e.g. user visits the bootstrap
        // link) and try again on the normal reconnect cadence.
        timerRef.current = setTimeout(connect, CONFIG.WS_RECONNECT_INTERVAL);
        return;
      }

      const url = `${WS_BASE}/ws/dashboard?token=${encodeURIComponent(token)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.event && msg.event !== 'ping') {
            onEventRef.current(msg.event, msg.data || {});
          }
        } catch (_) { }
      };

      ws.onclose = (e) => {
        wsRef.current = null;
        if (destroyed) return;

        if (e.code === WS_CLOSE_AUTH_FAILED) {
          // Stored token is stale/invalid — clear it so apiFetch() also
          // stops sending it, and surface the auth failure to the UI.
          clearDashboardToken();
          onAuthErrorRef.current?.();
        }
        timerRef.current = setTimeout(connect, CONFIG.WS_RECONNECT_INTERVAL);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      destroyed = true;
      clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, []); // eslint-disable-line
}