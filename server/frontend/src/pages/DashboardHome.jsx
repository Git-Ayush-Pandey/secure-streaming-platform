import React, { useState, useCallback } from 'react';
import { Wifi, Shield, Clock, AlertTriangle, Play, Square,
         RefreshCw, Radio, Activity, Database } from 'lucide-react';
import StatCard from '../components/StatCard';
import DeviceTable from '../components/DeviceTable';
import { useApp } from '../context/AppContext';
import { usePolling } from '../hooks/usePolling';
import { getConnected, removeDevice } from '../api/devices';
import { startStream, stopStream } from '../api/stream';

function fmtBytes(b) {
  if (!b) return '0 B';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1073741824) return `${(b / 1048576).toFixed(1)} MB`;
  return `${(b / 1073741824).toFixed(2)} GB`;
}

function fmtDuration(ts) {
  if (!ts) return '—';
  const secs = Math.floor(Date.now() / 1000 - ts);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

export default function DashboardHome() {
  const { serverInfo, pendingRequests, refreshServerInfo, refreshPending } = useApp();
  const [connected, setConnected] = useState([]);
  const [captureLoading, setCaptureLoading] = useState(false);

  const fetchConnected = useCallback(async () => {
    try {
      const { devices } = await getConnected();
      setConnected(devices);
    } catch (_) {}
  }, []);

  usePolling(fetchConnected, 4000);

  const [refreshing, setRefreshing] = useState(false);
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([
      refreshServerInfo(),
      fetchConnected(),
      refreshPending()
    ]);
    setRefreshing(false);
  }, [refreshServerInfo, fetchConnected, refreshPending]);

  // Capture running = screen is being grabbed
  const captureRunning = serverInfo?.capture_running;
  // UDP service running = frames being sent over UDP
  const udpRunning = serverInfo?.stream?.running;
  const cfg        = serverInfo?.config?.capture;

  // Stream stats from UDP service
  const stream     = serverInfo?.stream ?? {};
  const fpsActual  = stream.fps_actual ?? null;
  const bytesSent  = stream.bytes_sent ?? 0;
  const udpPort    = stream.udp_port ?? serverInfo?.config?.server?.port ?? 8765;
  const udpClients = stream.client_count ?? connected.length;

  async function toggleCapture() {
    setCaptureLoading(true);
    try {
      if (captureRunning) await stopStream();
      else await startStream();
      await refreshServerInfo();
    } catch (e) { console.error(e); }
    finally { setCaptureLoading(false); }
  }

  const connCols = [
    { key: 'actions', label: 'Actions', render: (row) => (
      <button
        className="btn btn-xs btn-error"
        onClick={async (e) => {
          e.stopPropagation();
          try {
            await removeDevice(row.fingerprint);
            await fetchConnected();
          } catch (err) {
            console.error('Remove failed', err);
          }
        }}
      >Remove</button>
    ) },
    { key: 'device_name', label: 'Device',       className: 'primary' },
    { key: 'ip',          label: 'IP Address' },
    { key: 'connected_at',label: 'Since',         render: r => fmtDuration(r.connected_at) },
    { key: 'frames_sent', label: 'Frames Sent',   render: r => (r.frames_sent ?? 0).toLocaleString() },
    { key: 'transport',   label: 'Transport',      render: () =>
        <span className="badge badge-connected"><span className="dot-pulse" />UDP</span> },
  ];

  return (
    <div>
      {/* Header */}
      <div className="flex-between mb-20">
        <div>
          <h1 className="page-title">Dashboard Overview</h1>
          <p className="page-subtitle">Real-time server status and connected device monitor</p>
        </div>
        <div className="flex gap-8">
          <button className="btn btn-ghost btn-sm" onClick={handleRefresh} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? 'spin' : ''} /> Refresh
          </button>
          <button
            id="toggle-capture-btn"
            className={`btn btn-sm ${captureRunning ? 'btn-danger' : 'btn-success'}`}
            onClick={toggleCapture}
            disabled={captureLoading}
          >
            {captureLoading
              ? <span className="spinner" style={{ width: 14, height: 14 }} />
              : captureRunning
                ? <><Square size={13} /> Stop Capture</>
                : <><Play size={13} /> Start Capture</>
            }
          </button>
        </div>
      </div>

      {/* Pending alerts */}
      {pendingRequests.length > 0 && (
        <div className="alert-banner mb-20">
          <AlertTriangle size={18} />
          <strong>
            {pendingRequests.length} device{pendingRequests.length > 1 ? 's' : ''} waiting for approval
          </strong>
          {' '}— a popup will appear with Approve / Reject options
        </div>
      )}

      {/* Stats grid */}
      <div className="stats-grid">
        {/* UDP clients (from stream stats — more accurate than polling) */}
        <StatCard
          label="UDP Clients"
          value={udpClients}
          sub="Receiving encrypted stream"
          icon={<Wifi size={28} />}
          color="var(--accent-green)"
        />
        <StatCard
          label="Pending Approval"
          value={pendingRequests.length}
          sub={pendingRequests.length > 0 ? 'Check popup modal' : 'No pending requests'}
          icon={<AlertTriangle size={28} />}
          color={pendingRequests.length > 0 ? 'var(--accent-orange)' : 'var(--text-muted)'}
        />
        {/* Actual vs target FPS */}
        <StatCard
          label="Actual FPS"
          value={fpsActual !== null ? fpsActual : '—'}
          sub={`Target: ${cfg?.fps ?? '—'} FPS · ${cfg?.quality ?? '—'} quality`}
          icon={<Activity size={28} />}
          color="var(--accent-cyan)"
        />
        {/* Frames captured total */}
        <StatCard
          label="Frames Captured"
          value={(serverInfo?.frame_count ?? 0).toLocaleString()}
          sub="Total since server start"
          icon={<Clock size={28} />}
          color="var(--accent-purple)"
        />
        {/* Bytes sent over UDP */}
        <StatCard
          label="Data Sent"
          value={fmtBytes(bytesSent)}
          sub={`UDP :${udpPort} · AES-256-GCM`}
          icon={<Database size={28} />}
          color="var(--accent-cyan)"
        />
        {/* Dual status: capture + UDP */}
        <StatCard
          label="Service Status"
          value={captureRunning && udpRunning ? 'LIVE' : captureRunning ? 'CAP' : 'OFF'}
          sub={
            captureRunning && udpRunning ? 'Capture + UDP running'
            : captureRunning ? 'Capture only (no UDP clients)'
            : 'Capture stopped'
          }
          icon={<Radio size={28} />}
          color={captureRunning ? 'var(--accent-green)' : 'var(--accent-red)'}
        />
      </div>

      {/* UDP status info bar */}
      <div style={{
        background: udpRunning
          ? 'rgba(0,255,136,0.05)' : 'rgba(255,68,102,0.05)',
        border: `1px solid ${udpRunning
          ? 'rgba(0,255,136,0.15)' : 'rgba(255,68,102,0.15)'}`,
        borderRadius: 10,
        padding: '10px 16px',
        marginBottom: 20,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        fontSize: 12,
      }}>
        <Radio size={14} color={udpRunning ? 'var(--accent-green)' : 'var(--accent-red)'} />
        <span style={{ color: 'var(--text-secondary)' }}>
          <strong style={{ color: udpRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}>
            UDP Stream Service
          </strong>
          {' '}{udpRunning ? `active on port ${udpPort}` : 'not running'}
          {' '}·{' '}
          <span style={{ fontFamily: 'JetBrains Mono' }}>
            Auth: X25519+HKDF · Heartbeat: HMAC-SHA256 · Frames: AES-GCM+seq
          </span>
        </span>
        {!udpRunning && (
          <span style={{ marginLeft: 'auto', color: 'var(--accent-orange)', fontWeight: 600 }}>
            Restart server to re-enable UDP
          </span>
        )}
      </div>

      {/* Connected devices table */}
      <div className="card">
        <div className="card-title">
          <Wifi size={14} />
          Active UDP Clients
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
            {connected.length} connected
          </span>
        </div>
        <DeviceTable
          columns={connCols}
          rows={connected.slice(0, 10)}
          loading={false}
          hasMore={false}
        />
      </div>

      {/* Server identity + security protocol */}
      <div className="grid-2 mt-20">
        <div className="card">
          <div className="card-title"><Shield size={14} /> Server Identity</div>
          <div style={{
            fontFamily: 'JetBrains Mono', fontSize: 12,
            color: 'var(--accent-cyan)', wordBreak: 'break-all', marginBottom: 8,
          }}>
            {serverInfo?.server_fingerprint ?? 'Loading…'}
          </div>
          <div style={{
            fontFamily: 'JetBrains Mono', fontSize: 11,
            color: 'var(--text-muted)', wordBreak: 'break-all',
          }}>
            {serverInfo?.server_public_key_b64?.slice(0, 64) ?? ''}…
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-muted)' }}>
            Private key encrypted at rest · passphrase-protected PEM
          </div>
        </div>

        <div className="card">
          <div className="card-title"><Radio size={14} /> Transport &amp; Security</div>
          <div style={{ display: 'grid', gap: 10 }}>
            {[
              { k: 'Auth Transport',    v: 'WebSocket /ws/auth' },
              { k: 'Stream Transport',  v: `UDP :${udpPort}` },
              { k: 'Key Exchange',      v: 'X25519 + HKDF-SHA256' },
              { k: 'Heartbeat Auth',    v: 'HMAC-SHA256 (session key)' },
              { k: 'Frame Encryption',  v: 'AES-256-GCM + seq AAD' },
              { k: 'Replay Protection', v: '±30s window + nonce history' },
              { k: 'Identity Signing',  v: 'Ed25519' },
              { k: 'Trust Model',       v: 'TOFU + Manual Approval' },
            ].map(row => (
              <div key={row.k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                <span style={{ color: 'var(--text-muted)' }}>{row.k}</span>
                <span style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono', fontSize: 11 }}>
                  {row.v}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
