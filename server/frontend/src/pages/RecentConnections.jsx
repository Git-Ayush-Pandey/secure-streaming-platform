import React, { useState, useCallback } from 'react';
import { Clock } from 'lucide-react';
import DeviceTable from '../components/DeviceTable';
import { usePolling } from '../hooks/usePolling';
import { getRecent } from '../api/devices';

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

const RESULT_BADGE = {
  connected: <span className="badge badge-connected">Connected</span>,
  pending:   <span className="badge badge-pending">Pending</span>,
  rejected:  <span className="badge badge-rejected">Rejected</span>,
  blocked:   <span className="badge badge-blocked">Blocked</span>,
};

const PAGE = 10;

const COLS = [
  { key: 'device_name', label: 'Device Name', className: 'primary' },
  { key: 'fingerprint', label: 'Fingerprint', className: 'mono',
    render: r => r.fingerprint?.slice(0, 20) + '…' },
  { key: 'ip', label: 'IP Address' },
  { key: 'timestamp', label: 'Time', render: r => fmtTime(r.timestamp) },
  { key: 'result', label: 'Result',
    render: r => RESULT_BADGE[r.result] || <span className="badge">{r.result}</span> },
];

export default function RecentConnections() {
  const [devices, setDevices] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async (off = 0, append = false) => {
    setLoading(true);
    try {
      const { devices: d, total: t } = await getRecent(PAGE, off);
      setDevices(prev => append ? [...prev, ...d] : d);
      setTotal(t);
    } catch (_) {}
    finally { setLoading(false); }
  }, []);

  usePolling(() => fetch(0, false), 10000);

  return (
    <div>
      <h1 className="page-title">Recent Connections</h1>
      <p className="page-subtitle">History of all connection attempts on this server</p>

      <div className="card">
        <div className="card-title">
          <Clock size={14} />
          Connection History
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
