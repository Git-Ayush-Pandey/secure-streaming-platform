import React, { useState, useCallback } from 'react';
import { Ban, RotateCcw, Shield } from 'lucide-react';
import DeviceTable from '../components/DeviceTable';
import { usePolling } from '../hooks/usePolling';
import { getBlocked, unblockDevice, trustBlocked } from '../api/devices';
import { CONFIG } from '../config';

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

const PAGE = 10;

export default function BlockedDevices() {
  const [devices, setDevices] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState({});

  const fetch = useCallback(async (off = 0, append = false) => {
    setLoading(true);
    try {
      const { devices: d, total: t } = await getBlocked(PAGE, off);
      setDevices(prev => append ? [...prev, ...d] : d);
      setTotal(t);
    } catch (_) {}
    finally { setLoading(false); }
  }, []);

  usePolling(
      () => fetch(0, false),
      CONFIG.DEVICE_REFRESH_INTERVAL
  );
  async function doUnblock(fp) {
    setActionLoading(p => ({ ...p, [fp]: 'unblock' }));
    try { await unblockDevice(fp); await fetch(0, false); }
    catch (e) { console.error(e); }
    finally { setActionLoading(p => ({ ...p, [fp]: null })); }
  }

  async function doTrust(fp) {
    setActionLoading(p => ({ ...p, [fp]: 'trust' }));
    try { await trustBlocked(fp); await fetch(0, false); }
    catch (e) { console.error(e); }
    finally { setActionLoading(p => ({ ...p, [fp]: null })); }
  }

  const COLS = [
    { key: 'device_name', label: 'Device Name', className: 'primary' },
    { key: 'fingerprint', label: 'Fingerprint', className: 'mono',
      render: r => r.fingerprint?.slice(0, 24) + '…' },
    { key: 'last_ip', label: 'Last IP' },
    { key: 'blocked_at', label: 'Blocked At', render: r => fmtTime(r.blocked_at) },
    { key: 'status', label: 'Status',
      render: () => <span className="badge badge-blocked"><Ban size={9} />Blocked</span> },
  ];

  return (
    <div>
      <h1 className="page-title">Blocked Devices</h1>
      <p className="page-subtitle">Devices permanently denied access to the stream</p>

      <div className="card">
        <div className="card-title">
          <Ban size={14} />
          Block List
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>{total} total</span>
        </div>
        <DeviceTable
          columns={COLS}
          rows={devices}
          loading={loading}
          hasMore={devices.length < total}
          onLoadMore={() => { const next = offset + PAGE; setOffset(next); fetch(next, true); }}
          actions={(row) => [
            <button
              key="unblock"
              id={`unblock-${row.fingerprint}`}
              className="btn btn-ghost btn-sm"
              disabled={!!actionLoading[row.fingerprint]}
              onClick={() => doUnblock(row.fingerprint)}
            >
              {actionLoading[row.fingerprint] === 'unblock'
                ? <span className="spinner" style={{width:12,height:12}} />
                : <RotateCcw size={12} />}
              Unblock
            </button>,
            <button
              key="trust"
              id={`trust-blocked-${row.fingerprint}`}
              className="btn btn-success btn-sm"
              disabled={!!actionLoading[row.fingerprint]}
              onClick={() => doTrust(row.fingerprint)}
            >
              {actionLoading[row.fingerprint] === 'trust'
                ? <span className="spinner" style={{width:12,height:12}} />
                : <Shield size={12} />}
              Trust Device
            </button>,
          ]}
        />
      </div>
    </div>
  );
}
