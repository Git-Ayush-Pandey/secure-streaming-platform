import React, { useState, useCallback } from 'react';
import { Wifi, Info } from 'lucide-react';
import DeviceTable from '../components/DeviceTable';
import { usePolling } from '../hooks/usePolling';
import { getConnected } from '../api/devices';
import { useApp } from '../context/AppContext';
import { CONFIG } from '../config';

function fmtDuration(ts) {
  if (!ts) return '—';
  const secs = Math.floor(Date.now() / 1000 - ts);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

const COLS = [
  { key: 'device_name',  label: 'Device Name',   className: 'primary' },
  { key: 'fingerprint',  label: 'Fingerprint',    className: 'mono',
    render: r => (r.fingerprint?.slice(0, 20) + '…') },
  { key: 'ip',           label: 'IP Address' },
  { key: 'connected_at', label: 'Connected Since', render: r => fmtDuration(r.connected_at) },
  { key: 'frames_sent',  label: 'Frames Sent',    render: r => (r.frames_sent ?? 0).toLocaleString() },
  { key: 'transport',    label: 'Transport',
    render: () => (
      <span className="badge badge-connected">
        <span className="dot-pulse" />UDP AES-GCM
      </span>
    )},
];

export default function ConnectedDevices() {
  const { serverInfo } = useApp();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    try {
      const { devices: d } = await getConnected();
      setDevices(d);
    } catch (_) {}
    finally { setLoading(false); }
  }, []);

  usePolling(fetch, CONFIG.POLL_INTERVAL);

  const udpPort   = serverInfo?.stream?.udp_port ?? serverInfo?.config?.server?.port ?? 8765;
  const fpsActual = serverInfo?.stream?.fps_actual ?? '—';

  return (
    <div>
      <h1 className="page-title">Connected Devices</h1>
      <p className="page-subtitle">
        Devices currently receiving AES-256-GCM encrypted frames over UDP
      </p>

      {/* Protocol info banner */}
      <div style={{
        background: 'rgba(0,212,255,0.05)',
        border: '1px solid rgba(0,212,255,0.12)',
        borderRadius: 10,
        padding: '12px 16px',
        marginBottom: 20,
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        fontSize: 12,
        color: 'var(--text-secondary)',
      }}>
        <Info size={14} color="var(--accent-cyan)" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <strong style={{ color: 'var(--accent-cyan)' }}>UDP stream on port {udpPort}</strong>
          {' '}· Actual FPS: <strong>{fpsActual}</strong>
          {' '}· Clients must send HMAC-SHA256 authenticated heartbeat packets every ~5s to stay registered.
          Clients silent for {'>'}30s are automatically evicted.
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <Wifi size={14} />
          UDP Clients
          <span style={{ marginLeft: 'auto', color: 'var(--accent-green)', fontWeight: 700, fontSize: 13 }}>
            {devices.length} active
          </span>
        </div>
        <DeviceTable columns={COLS} rows={devices} loading={loading} hasMore={false} />
      </div>
    </div>
  );
}
