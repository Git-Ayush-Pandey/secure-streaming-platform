import React, { useState, useEffect } from 'react';
import { AlertTriangle, X, Timer } from 'lucide-react';
import {
  approvePending, allowOncePending, rejectPending, blockPending,
} from '../api/devices';
import { useApp } from '../context/AppContext';

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

/** Live countdown using expires_in from backend (challenge TTL = 60s) */
function ExpiryCountdown({ expiresIn }) {
  const [secs, setSecs] = useState(Math.max(0, Math.floor(expiresIn ?? 60)));

  useEffect(() => {
    if (secs <= 0) return;
    const id = setInterval(() => setSecs(s => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line

  const urgent = secs < 15;
  const color  = secs === 0
    ? 'var(--accent-red)'
    : urgent ? 'var(--accent-orange)' : 'var(--text-muted)';

  return (
    <span style={{
      fontFamily: 'JetBrains Mono',
      fontSize: 11,
      color,
      fontWeight: urgent ? 700 : 400,
    }}>
      {secs === 0
        ? '⚠ Challenge expired — client must reconnect'
        : `Challenge expires in ${secs}s`}
    </span>
  );
}

function PendingCard({ device, onDismiss }) {
  const [loading, setLoading] = useState(null);
  const { removePending } = useApp();

  async function act(label, apiFn) {
    setLoading(label);
    try {
      await apiFn(device.fingerprint);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(null);
      removePending(device.fingerprint);
      onDismiss?.(device.fingerprint);
    }
  }

  const isExpired = (device.expires_in ?? 60) <= 0;

  return (
    <div
      className="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onDismiss?.(device.fingerprint)}
    >
      <div className="modal-box">
        {/* Header */}
        <div className="modal-header">
          <div className="modal-icon">
            <AlertTriangle size={22} />
          </div>
          <div>
            <div className="modal-title">New Device Requesting Access</div>
            <div className="modal-subtitle">
              Review and decide how to handle this connection request
            </div>
          </div>
          <button
            className="btn btn-ghost btn-icon"
            style={{ marginLeft: 'auto' }}
            onClick={() => onDismiss?.(device.fingerprint)}
          >
            <X size={16} />
          </button>
        </div>

        {/* Expiry warning bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          marginBottom: 16,
          borderRadius: 8,
          background: 'rgba(0,0,0,0.25)',
          border: '1px solid var(--border)',
        }}>
          <Timer size={13} color="var(--text-muted)" />
          <ExpiryCountdown expiresIn={device.expires_in} />
        </div>

        {/* Device info */}
        <div className="modal-info">
          <div className="modal-info-row">
            <span className="modal-info-key">Device Name</span>
            <span className="modal-info-val">{device.device_name || device.device_id || '—'}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-info-key">IP Address</span>
            <span className="modal-info-val">{device.ip}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-info-key">Fingerprint</span>
            <span className="modal-info-val mono">{device.fingerprint}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-info-key">Requested At</span>
            <span className="modal-info-val">{fmtTime(device.timestamp)}</span>
          </div>
          <div className="modal-info-row">
            <span className="modal-info-key">Auth Method</span>
            <span className="modal-info-val" style={{ fontFamily: 'JetBrains Mono', fontSize: 11 }}>
              Ed25519 + X25519/HKDF
            </span>
          </div>
        </div>

        {/* Expired state */}
        {isExpired ? (
          <div style={{
            textAlign: 'center', padding: '16px 0',
            color: 'var(--accent-red)', fontSize: 13, fontWeight: 600,
          }}>
            Challenge expired — client must reconnect to request again
            <div style={{ marginTop: 10 }}>
              <button
                className="btn btn-ghost"
                onClick={() => onDismiss?.(device.fingerprint)}
              >
                Dismiss
              </button>
            </div>
          </div>
        ) : (
          /* Action buttons */
          <div className="modal-actions">
            <button
              id={`approve-${device.fingerprint}`}
              className="btn btn-success"
              disabled={!!loading}
              onClick={() => act('approve', approvePending)}
            >
              {loading === 'approve'
                ? <span className="spinner" style={{ width: 14, height: 14 }} />
                : '✓'}
              Approve Permanently
            </button>

            <button
              id={`allow-once-${device.fingerprint}`}
              className="btn btn-ghost"
              disabled={!!loading}
              onClick={() => act('allow_once', allowOncePending)}
            >
              {loading === 'allow_once'
                ? <span className="spinner" style={{ width: 14, height: 14 }} />
                : '~'}
              Allow Once
            </button>

            <button
              id={`reject-${device.fingerprint}`}
              className="btn btn-ghost"
              disabled={!!loading}
              onClick={() => act('reject', rejectPending)}
            >
              {loading === 'reject'
                ? <span className="spinner" style={{ width: 14, height: 14 }} />
                : '✕'}
              Reject
            </button>

            <button
              id={`block-${device.fingerprint}`}
              className="btn btn-danger"
              disabled={!!loading}
              onClick={() => act('block', blockPending)}
            >
              {loading === 'block'
                ? <span className="spinner" style={{ width: 14, height: 14 }} />
                : '⊘'}
              Block Permanently
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PendingModal() {
  const { pendingRequests } = useApp();
  const [dismissed, setDismissed] = useState(new Set());

  // Only show non-dismissed, non-expired pending requests
  const visible = pendingRequests.filter(
    r => !dismissed.has(r.fingerprint) && (r.expires_in ?? 60) > 0
  );

  if (!visible.length) return null;

  const current = visible[0];

  return (
    <PendingCard
      device={current}
      onDismiss={(fp) => setDismissed(prev => new Set([...prev, fp]))}
    />
  );
}
