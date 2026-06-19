import React, { useEffect, useRef } from 'react';

/**
 * Event → CSS class mapping.
 * Covers all events emitted by the hardened backend.
 */
const EVENT_CLASS = {
  // Connection lifecycle
  CLIENT_CONNECTED:         'connected',
  CLIENT_CONNECTED_UDP:     'connected',
  CLIENT_DISCONNECTED:      'disconnected',
  CLIENT_DISCONNECTED_UDP:  'disconnected',
  CLIENT_TIMEOUT_UDP:       'disconnected',

  // Auth & trust
  CLIENT_TRUSTED:           'trusted',
  CLIENT_AUTHENTICATED:     'trusted',
  CLIENT_BLOCKED:           'blocked',
  CLIENT_REJECTED:          'rejected',
  ALLOW_ONCE:               'auth',
  PENDING_REQUEST:          'auth',
  PENDING_EVICTED:          'auth',

  // Auth failures & security events
  AUTH_FAILURE:             'auth_fail',
  RATE_LIMIT_EXCEEDED:      'security',
  UDP_HEARTBEAT_HMAC_FAIL:  'security',
  UDP_HEARTBEAT_REPLAY:     'security',
  UDP_HEARTBEAT_NONCE_REPLAY:'security',
  UDP_UNAUTHENTICATED_HEARTBEAT:'security',
  SECURITY_WARNING:         'security',
  LEGACY_KEY_DELIVERY:      'warning',
  DASHBOARD_WS_LIMIT:       'warning',

  // Session & challenge expiry
  SESSION_EXPIRED:          'expiry',
  CHALLENGE_EXPIRED:        'expiry',

  // Stream lifecycle
  STREAM_STARTED:           'stream',
  STREAM_STOPPED:           'stream',
  STREAM_CONFIGURED:        'stream',
  UDP_SERVER_STARTED:       'stream',
  UDP_SERVER_STOPPED:       'stream',

  // Capture service
  CAPTURE_STARTED:          'stream',
  CAPTURE_STOPPED:          'stream',
  CAPTURE_FRAME_ERROR:      'warning',
  CAPTURE_LOOP_FATAL:       'error',
  CAPTURE_SUSPENDED:        'warning',
  CAPTURE_DEMO_MODE:        'warning',
  CAPTURE_DEMO_FRAME_ERROR: 'warning',
  CAPTURE_IMPORT_WARNING:   'warning',

  // UDP transport
  UDP_SEND_ERROR:           'error',
  UDP_ERROR:                'error',
  UDP_START_FAILED:         'error',
  UDP_MALFORMED_HEARTBEAT:  'warning',
  UDP_HEARTBEAT_BAD_TS:     'warning',
  UDP_UNAUTH_PACKET:        'warning',
};

function fmtTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function fmtData(data) {
  if (!data || Object.keys(data).length === 0) return '';
  return JSON.stringify(data);
}

export default function LogViewer({ logs = [], autoScroll = true }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  if (!logs.length) {
    return (
      <div className="log-container" style={{
        padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)',
      }}>
        No log entries yet. Start the backend to see events.
      </div>
    );
  }

  return (
    <div className="log-container">
      {logs.map((log, i) => {
        const eventKey = log.event || log.type || '';
        const cls      = EVENT_CLASS[eventKey] || 'default';
        const dataStr  = fmtData(log.data);
        return (
          <div className="log-row" key={i}>
            <span className="log-time">{fmtTimestamp(log.timestamp)}</span>
            <span className={`log-event ${cls}`}>{eventKey}</span>
            {dataStr && <span className="log-data">{dataStr}</span>}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
