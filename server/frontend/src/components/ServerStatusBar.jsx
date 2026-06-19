import React from 'react';
import { Activity, Camera, Layers, Cpu, Radio, Wifi } from 'lucide-react';
import { useApp } from '../context/AppContext';

function fmtBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function ServerStatusBar() {
  const { serverInfo, serverError } = useApp();

  const isRunning = serverInfo?.capture_running;
  const fps       = serverInfo?.config?.capture?.fps ?? '—';
  const quality   = serverInfo?.config?.capture?.quality ?? '—';
  const codec     = serverInfo?.config?.capture?.codec ?? serverInfo?.stream?.codec ?? '—';
  const frames    = serverInfo?.frame_count ?? 0;
  const fp        = serverInfo?.server_fingerprint ?? '—';

  // New stream stats from UDP service
  const stream      = serverInfo?.stream ?? {};
  const udpPort     = stream.udp_port ?? serverInfo?.config?.server?.port ?? '—';
  const fpsActual   = stream.fps_actual ?? '—';
  const bytesSent   = stream.bytes_sent ?? 0;
  const clientCount = stream.client_count ?? 0;

  return (
    <header className="status-bar">
      {/* Capture status */}
      <div className={`status-item ${isRunning ? 'live' : 'offline'}`}>
        <span className="dot-pulse"
          style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }} />
        <strong>{isRunning ? 'Capture LIVE' : 'Capture Stopped'}</strong>
      </div>

      <div className="status-divider" />

      {/* Target FPS */}
      <div className="status-item">
        <Activity size={13} color="var(--accent-cyan)" />
        <span>Target: <strong>{fps} FPS</strong></span>
      </div>

      <div className="status-divider" />

      {/* Actual FPS */}
      <div className="status-item">
        <Radio size={13} color="var(--accent-green)" />
        <span>Actual: <strong style={{ color: 'var(--accent-green)' }}>
          {fpsActual !== '—' ? `${fpsActual} FPS` : '—'}
        </strong></span>
      </div>

      <div className="status-divider" />



      <div className="status-divider" />

      <div className="status-item">
        <Layers size={13} color="var(--text-muted)" />
        <span>Codec: <strong style={{ fontFamily: 'JetBrains Mono', textTransform: 'uppercase' }}>
          {codec === '—' ? '—' : codec === 'h264' ? 'H.264' : 'JPEG'}
        </strong></span>
      </div>

      <div className="status-divider" />

      {/* Frames captured */}
      <div className="status-item">
        <Layers size={13} color="var(--accent-cyan)" />
        <span>Frames: <strong>{frames.toLocaleString()}</strong></span>
      </div>

      <div className="status-divider" />

      {/* UDP port + connected count */}
      <div className="status-item">
        <Wifi size={13} color={clientCount > 0 ? 'var(--accent-green)' : 'var(--text-muted)'} />
        <span>
          UDP <strong style={{ fontFamily: 'JetBrains Mono', fontSize: 12 }}>:{udpPort}</strong>
          &nbsp;·&nbsp;
          <strong style={{ color: clientCount > 0 ? 'var(--accent-green)' : 'var(--text-muted)' }}>
            {clientCount} client{clientCount !== 1 ? 's' : ''}
          </strong>
        </span>
      </div>

      <div className="status-divider" />

      {/* Bytes sent */}
      <div className="status-item">
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Sent: <strong style={{ color: 'var(--text-secondary)' }}>{fmtBytes(bytesSent)}</strong>
        </span>
      </div>

      {/* Right: Server fingerprint + error */}
      <div className="status-bar-right">
        <div className="status-item">
          <Cpu size={13} color="var(--text-muted)" />
          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--text-muted)' }}>
            {fp !== '—' ? `${fp.slice(0, 24)}…` : 'Connecting…'}
          </span>
        </div>

        {serverError && (
          <div style={{
            background: 'rgba(255,68,102,0.15)',
            border: '1px solid rgba(255,68,102,0.3)',
            borderRadius: 6,
            padding: '3px 10px',
            fontSize: 11,
            color: 'var(--accent-red)',
            fontWeight: 600,
          }}>
            Backend Unreachable
          </div>
        )}
      </div>
    </header>
  );
}
