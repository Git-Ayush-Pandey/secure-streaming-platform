import React, { useState, useCallback } from 'react';
import { Shield, Zap, Users, FileText, Activity, AlertTriangle, CheckCircle } from 'lucide-react';
import { useApp } from '../context/AppContext';
import { usePolling } from '../hooks/usePolling';
import { apiFetch } from '../api/api';

function getSecurityStats() {
  return apiFetch('/api/server/security');
}

function Gauge({ label, value, max, unit = '', color = 'var(--accent-cyan)', warn, danger }) {
  const pct   = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const isWarn   = warn   != null && value >= warn;
  const isDanger = danger != null && value >= danger;
  const barColor = isDanger ? 'var(--accent-red)'
                 : isWarn   ? 'var(--accent-orange)'
                 : color;

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
        <span style={{ color: barColor, fontFamily: 'JetBrains Mono', fontWeight: 700 }}>
          {value.toLocaleString()}{unit}
          {max != null && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> / {max.toLocaleString()}{unit}</span>}
        </span>
      </div>
      {max != null && (
        <div style={{ height: 5, background: 'rgba(255,255,255,0.07)', borderRadius: 3, overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${pct}%`,
            background: barColor,
            borderRadius: 3,
            transition: 'width 0.4s ease',
          }} />
        </div>
      )}
    </div>
  );
}

function Counter({ label, value, note, alert }) {
  const color = alert && value > 0 ? 'var(--accent-orange)' : 'var(--text-muted)';
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
      padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 12,
    }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <div style={{ textAlign: 'right' }}>
        <span style={{ color, fontFamily: 'JetBrains Mono', fontWeight: 700 }}>
          {value.toLocaleString()}
        </span>
        {note && <div style={{ color: 'var(--text-muted)', fontSize: 10 }}>{note}</div>}
      </div>
    </div>
  );
}

export default function SecurityMonitor() {
  const { serverInfo } = useApp();
  const [sec, setSec]     = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const fetch = useCallback(async () => {
    try {
      const data = await getSecurityStats();
      setSec(data);
      setLastUpdate(new Date());
    } catch (_) {}
  }, []);

  usePolling(fetch, 2000);

  const stream   = serverInfo?.stream ?? {};
  const udp      = sec?.udp_rate_limit ?? {};
  const auth     = sec?.auth ?? {};
  const logging  = sec?.logging ?? {};

  const dropped  = udp.packets_dropped_rate_limit ?? 0;
  const rejected = udp.packets_rejected_auth ?? 0;
  const clientsRejected = udp.clients_rejected_limit ?? 0;
  const currentClients  = stream.client_count ?? udp.current_stream_clients ?? 0;
  const maxClients      = udp.max_stream_clients ?? 16;

  const currentPending = auth.current_pending ?? 0;
  const maxPending     = auth.max_pending ?? 100;

  const fpsActual = stream.fps_actual ?? 0;
  const bytesSent = stream.bytes_sent ?? 0;

  const anyAlert = dropped > 0 || rejected > 0 || clientsRejected > 0;

  return (
    <div>
      <h1 className="page-title">Security Monitor</h1>
      <p className="page-subtitle">
        Real-time DoS protection counters, client limits, and stream health
      </p>

      {/* Overall threat indicator */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 16px', borderRadius: 10, marginBottom: 20,
        background: anyAlert ? 'rgba(255,136,0,0.07)' : 'rgba(0,255,136,0.05)',
        border: `1px solid ${anyAlert ? 'rgba(255,136,0,0.25)' : 'rgba(0,255,136,0.15)'}`,
        fontSize: 13,
      }}>
        {anyAlert
          ? <AlertTriangle size={16} color="var(--accent-orange)" />
          : <CheckCircle   size={16} color="var(--accent-green)"  />}
        <strong style={{ color: anyAlert ? 'var(--accent-orange)' : 'var(--accent-green)' }}>
          {anyAlert ? 'Anomalous traffic detected' : 'No threats detected'}
        </strong>
        {anyAlert && (
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            — review counters below. All protection layers active.
          </span>
        )}
        {lastUpdate && (
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 11 }}>
            Updated {lastUpdate.toLocaleTimeString()}
          </span>
        )}
      </div>

      <div className="grid-2">

        {/* UDP Protection */}
        <div className="card">
          <div className="card-title"><Zap size={14} /> UDP Flood Protection</div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.6 }}>
            Packets from any IP exceeding <strong style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono' }}>200 pkt/s</strong> are dropped
            before parsing or HMAC verification. Counter is cumulative since server start.
          </p>

          <Gauge
            label="Stream clients"
            value={currentClients}
            max={maxClients}
            warn={maxClients * 0.75}
            danger={maxClients}
            color="var(--accent-green)"
          />

          <Counter
            label="Packets dropped (rate limit)"
            value={dropped}
            note="per-IP flood protection"
            alert
          />
          <Counter
            label="Packets rejected (auth failure)"
            value={rejected}
            note="no session / bad HMAC"
            alert
          />
          <Counter
            label="Clients rejected (capacity)"
            value={clientsRejected}
            note={`max ${maxClients} concurrent`}
            alert
          />
        </div>

        {/* Auth Protection */}
        <div className="card">
          <div className="card-title"><Shield size={14} /> Authentication Limits</div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.6 }}>
            HELLO rate: <strong style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono' }}>10/min/IP</strong>.
            New unknown fingerprints: <strong style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono' }}>5/min/IP</strong>.
            Protects the pending queue from key-pair spam.
          </p>

          <Gauge
            label="Pending queue"
            value={currentPending}
            max={maxPending}
            warn={maxPending * 0.5}
            danger={maxPending * 0.9}
            color="var(--accent-cyan)"
          />

          <Counter
            label="HELLO rate limit"
            value={auth.rate_limit_max_hellos ?? 10}
            unit=" / min / IP"
            note="per-IP sliding window"
          />
          <Counter
            label="New fingerprint limit"
            value={auth.pending_fp_limit_per_min ?? 5}
            unit=" / min / IP"
            note="bounds key-pair flooding"
          />
          <Counter
            label="Session TTL"
            value={30}
            unit=" min"
            note="sessions expire after inactivity"
          />
          <Counter
            label="Challenge TTL"
            value={60}
            unit=" sec"
            note="unanswered challenges expire"
          />
        </div>

        {/* Stream health */}
        <div className="card">
          <div className="card-title"><Activity size={14} /> Stream Health</div>

          <Gauge
            label="Actual FPS"
            value={fpsActual}
            max={serverInfo?.config?.capture?.fps ?? 30}
            color="var(--accent-green)"
            warn={(serverInfo?.config?.capture?.fps ?? 30) * 0.5}
          />

          <Counter label="UDP clients" value={currentClients} note="currently receiving frames" />
          <Counter
            label="Data sent (total)"
            value={0}
            note={fmtBytes(bytesSent)}
          />
          <Counter label="Frames captured" value={serverInfo?.frame_count ?? 0} />
          <Counter
            label="Codec"
            value={0}
            note={(stream.codec ?? serverInfo?.config?.capture?.codec ?? '—').toUpperCase()}
          />
        </div>

        {/* Log protection */}
        <div className="card">
          <div className="card-title"><FileText size={14} /> Log Rotation</div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.6 }}>
            Log files rotate at <strong style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono' }}>10 MB</strong>,
            keeping the newest <strong style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono' }}>5 files</strong>.
            The in-memory queue is capped at 10 000 entries — excess records are silently dropped during a flood.
          </p>

          <Counter label="Max file size" value={0} note="10 MB per daily log file" />
          <Counter label="Max files kept" value={0} note="5 files, oldest deleted on rotation" />
          <Counter label="Queue cap" value={0} note="10 000 entries in memory" />

          <div style={{
            marginTop: 12, padding: '8px 12px', borderRadius: 8,
            background: 'rgba(0,212,255,0.05)',
            border: '1px solid rgba(0,212,255,0.12)',
            fontSize: 11, color: 'var(--text-muted)',
          }}>
            A 50 000-packet flood producing one log entry each would fill ~5 MB —
            well within one rotation cycle. Rotation prevents disk exhaustion.
          </div>
        </div>

      </div>

      {/* Limits summary */}
      <div className="card mt-20">
        <div className="card-title"><Users size={14} /> Active Protection Summary</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10, marginTop: 4 }}>
          {[
            { label: 'UDP rate limit',        value: '200 pkt/s / IP',    ok: true  },
            { label: 'Max stream clients',     value: `${maxClients}`,     ok: true  },
            { label: 'HELLO rate limit',       value: '10 / min / IP',     ok: true  },
            { label: 'New FP rate limit',      value: '5 / min / IP',      ok: true  },
            { label: 'Max pending queue',      value: '100',               ok: true  },
            { label: 'Challenge TTL',          value: '60 s',              ok: true  },
            { label: 'Session TTL',            value: '30 min',            ok: true  },
            { label: 'Log rotation',           value: '10 MB / 5 files',   ok: true  },
            { label: 'Dashboard WS limit',     value: '10 connections',    ok: true  },
            { label: 'Nonce replay window',    value: '64 nonces / client',ok: true  },
            { label: 'Timestamp skew guard',   value: '±30 s',             ok: true  },
          ].map(r => (
            <div key={r.label} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '7px 10px', borderRadius: 7,
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--border)',
              fontSize: 11,
            }}>
              <span style={{ color: 'var(--text-muted)' }}>{r.label}</span>
              <span style={{ color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono', fontSize: 11 }}>
                {r.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function fmtBytes(b) {
  if (!b) return '0 B';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1073741824) return `${(b / 1048576).toFixed(1)} MB`;
  return `${(b / 1073741824).toFixed(2)} GB`;
}
