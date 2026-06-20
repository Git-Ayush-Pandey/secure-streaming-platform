import React, { createContext, useContext, useReducer, useCallback, useEffect } from 'react';
import { getServerInfo } from '../api/server';
import { getPending } from '../api/devices';
import { useDashboardSocket } from '../hooks/useDashboardSocket';
import { usePolling } from '../hooks/usePolling';
import { CONFIG } from '../config';
import { DashboardAuthError } from '../api/api';
import { getDashboardToken } from '../api/dashboardToken';

const AppContext = createContext(null);

const initialState = {
  serverInfo: null,
  serverError: false,
  needsAuth: !getDashboardToken(), // F1: no token stored yet
  pendingRequests: [],   // list of pending device objects (include expires_in)
  notifications: [],   // toast-style notifications
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_SERVER_INFO':
      return { ...state, serverInfo: action.payload, serverError: false };

    case 'SET_SERVER_ERROR':
      return { ...state, serverError: true };

    case 'SET_NEEDS_AUTH':
      return { ...state, needsAuth: true };

    case 'CLEAR_NEEDS_AUTH':
      return { ...state, needsAuth: false, serverError: false };

    case 'SET_PENDING': {
      // Filter out already-expired challenges from the polled list
      const now = Date.now() / 1000;
      const fresh = (action.payload || []).filter(r =>
        r.expires_in == null || r.expires_in > 0
      );
      return { ...state, pendingRequests: fresh };
    }

    case 'ADD_PENDING': {
      const exists = state.pendingRequests.find(
        r => r.fingerprint === action.payload.fingerprint
      );
      if (exists) return state;
      return { ...state, pendingRequests: [action.payload, ...state.pendingRequests] };
    }

    case 'REMOVE_PENDING':
      return {
        ...state,
        pendingRequests: state.pendingRequests.filter(
          r => r.fingerprint !== action.payload
        ),
      };

    // Tick down expires_in for all pending requests (called every second)
    case 'TICK_PENDING':
      return {
        ...state,
        pendingRequests: state.pendingRequests
          .map(r =>
            r.expires_in != null
              ? { ...r, expires_in: Math.max(0, r.expires_in - 1) }
              : r
          ),
      };

    case 'ADD_NOTIFICATION':
      return {
        ...state,
        notifications: [action.payload, ...state.notifications].slice(0, 10),
      };
    case 'REMOVE_NOTIFICATION':
      return {
        ...state,
        notifications: state.notifications.filter(n => n.id !== action.payload),
      };
    default:
      return state;
  }
}

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  // ── Server info polling (includes stream stats) ────────────────────────────
  const fetchServerInfo = useCallback(async () => {
    try {
      const info = await getServerInfo();
      dispatch({ type: 'SET_SERVER_INFO', payload: info });
      dispatch({ type: 'CLEAR_NEEDS_AUTH' });
    } catch (err) {
      if (err instanceof DashboardAuthError) {
        dispatch({ type: 'SET_NEEDS_AUTH' });
      } else {
        dispatch({ type: 'SET_SERVER_ERROR' });
      }
    }
  }, []);

  // ── Pending devices polling (fallback — WS is primary source) ─────────────
  const fetchPending = useCallback(async () => {
    try {
      const { devices } = await getPending();
      dispatch({ type: 'SET_PENDING', payload: devices });
    } catch (_) { }
  }, []);

  usePolling(fetchServerInfo, CONFIG.LOG_REFRESH_INTERVAL);
  usePolling(fetchPending, 8000);

  // ── Client-side challenge TTL countdown (tick every second) ───────────────
  useEffect(() => {
    const id = setInterval(() => {
      dispatch({ type: 'TICK_PENDING' });
    }, 1000);
    return () => clearInterval(id);
  }, []);

  // ── Live dashboard WebSocket events ───────────────────────────────────────
  const handleWsEvent = useCallback((event, data) => {
    if (event === 'pending_request') {
      // Backend includes expires_in — default to 60 (CHALLENGE_TTL)
      const payload = { expires_in: 60, ...data };
      dispatch({ type: 'ADD_PENDING', payload });
      dispatch({
        type: 'ADD_NOTIFICATION',
        payload: {
          id: Date.now(),
          type: 'pending',
          message: `New device requesting access: ${data.device_name || data.device_id}`,
          data: payload,
        },
      });
    }
  }, []);

  const handleWsAuthError = useCallback(() => {
    dispatch({ type: 'SET_NEEDS_AUTH' });
  }, []);

  useDashboardSocket(handleWsEvent, handleWsAuthError);

  // ── Helpers exposed to consumers ──────────────────────────────────────────
  const removePending = useCallback((fp) => {
    dispatch({ type: 'REMOVE_PENDING', payload: fp });
  }, []);

  const dismissNotification = useCallback((id) => {
    dispatch({ type: 'REMOVE_NOTIFICATION', payload: id });
  }, []);

  return (
    <AppContext.Provider
      value={{
        ...state,
        dispatch,
        removePending,
        dismissNotification,
        refreshServerInfo: fetchServerInfo,
        refreshPending: fetchPending,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}