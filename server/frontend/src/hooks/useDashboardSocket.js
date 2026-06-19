import { useEffect, useRef } from 'react';
import { WS_BASE } from '../api/api';
import { CONFIG } from '../config';
/**
 * Connects to /ws/dashboard and calls onEvent(event, data) for each message.
 * Auto-reconnects every {CONFIG.WS_RECONNECT_INTERVAL} ms on disconnect.
 */
export function useDashboardSocket(onEvent) {
  const wsRef     = useRef(null);
  const timerRef  = useRef(null);
  const onEventRef = useRef(onEvent);

  // Keep ref current without re-running effect
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      const ws = new WebSocket(`${WS_BASE}/ws/dashboard`);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.event && msg.event !== 'ping') {
            onEventRef.current(msg.event, msg.data || {});
          }
        } catch (_) {}
      };

      ws.onclose = () => {
        if (!destroyed) {
          timerRef.current = setTimeout(connect, CONFIG.WS_RECONNECT_INTERVAL);
        }
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
