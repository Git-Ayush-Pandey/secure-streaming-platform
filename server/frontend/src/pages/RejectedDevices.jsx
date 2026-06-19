import React, { useState, useCallback } from 'react';
import { XCircle } from 'lucide-react';
import DeviceTable from '../components/DeviceTable';
import { usePolling } from '../hooks/usePolling';
import { getRejected } from '../api/devices';
import { CONFIG } from '../config';

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

const PAGE = 10;

const COLS = [
  { key: 'device_name', label: 'Device Name', className: 'primary' },
  { key: 'fingerprint', label: 'Fingerprint', className: 'mono',
    render: r => r.fingerprint?.slice(0, 20) + '…' },
  { key: 'ip', label: 'IP Address' },
  { key: 'timestamp', label: 'Rejected At', render: r => fmtTime(r.timestamp) },
  { key: 'reason', label: 'Reason', render: r => (
    <span style={{ color: 'var(--accent-red)', fontSize: 12 }}>{r.reason || '—'}</span>
  )},
  { key: 'status', label: 'Status',
    render: () => <span className="badge badge-rejected"><XCircle size={9} />Rejected</span> },
];

export default function RejectedDevices() {
  const [devices, setDevices] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async (off = 0, append = false) => {
    setLoading(true);
    try {
      const { devices: d, total: t } = await getRejected(PAGE, off);
      setDevices(prev => append ? [...prev, ...d] : d);
      setTotal(t);
    } catch (_) {}
    finally { setLoading(false); }
  }, []);

  usePolling(
      () => fetch(0, false),
      CONFIG.DEVICE_REFRESH_INTERVAL
  );
  return (
    <div>
      <h1 className="page-title">Rejected Devices</h1>
      <p className="page-subtitle">Devices that were denied access — manually or due to auth failure</p>

      <div className="card">
        <div className="card-title">
          <XCircle size={14} />
          Rejection Log
          <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>{total} records</span>
        </div>
        <DeviceTable
          columns={COLS}
          rows={devices}
          loading={loading}
          hasMore={devices.length < total}
          onLoadMore={() => { const next = offset + PAGE; setOffset(next); fetch(next, true); }}
        />
      </div>
    </div>
  );
}
