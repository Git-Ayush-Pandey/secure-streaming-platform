import React, { useState, useCallback } from 'react';
import { Shield, Trash2, Ban } from 'lucide-react';
import DeviceTable from '../components/DeviceTable';
import { usePolling } from '../hooks/usePolling';
import { getTrusted, removeTrust, blockTrusted } from '../api/devices';

function fmtTime(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

const PAGE = 10;

export default function TrustedDevices() {
  const [devices, setDevices] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState({});

  const fetch = useCallback(async (off = 0, append = false) => {
    setLoading(true);
    try {
      const { devices: d, total: t } = await getTrusted(PAGE, off);
      setDevices(prev => append ? [...prev, ...d] : d);
      setTotal(t);
    } catch (_) {}
    finally { setLoading(false); }
  }, []);

  usePolling(() => fetch(0, false), 10000);

  async function doRemoveTrust(fp) {
    setActionLoading(p => ({ ...p, [fp]: 'remove' }));
    try { await removeTrust(fp); await fetch(0, false); }
    catch (e) { console.error(e); }
    finally { setActionLoading(p => ({ ...p, [fp]: null })); }
  }

  async function doBlock(fp) {
    setActionLoading(p => ({ ...p, [fp]: 'block' }));
    try { await blockTrusted(fp); await fetch(0, false); }
    catch (e) { console.error(e); }
    finally { setActionLoading(p => ({ ...p, [fp]: null })); }
  }

  const COLS = [
    { key: 'device_name', label: 'Device Name', className: 'primary' },
    { key: 'fingerprint', label: 'Fingerprint', className: 'mono',
      render: r => r.fingerprint?.slice(0, 24) + '…' },
    { key: 'last_ip', label: 'Last IP' },
    { key: 'first_approved', label: 'First Approved', render: r => fmtTime(r.first_approved) },
    { key: 'last_seen', label: 'Last Seen', render: r => fmtTime(r.last_seen) },
    { key: 'status', label: 'Status',
      render: () => <span className="badge badge-trusted"><Shield size={9} />Trusted</span> },
  ];

  return (
    <div>
      <h1 className="page-title">Trusted Devices</h1>
      <p className="page-subtitle">Permanently approved devices that can access the stream without manual approval</p>

      <div className="card">
        <div className="card-title">
          <Shield size={14} />
          Trusted List
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
              key="remove"
              id={`remove-trust-${row.fingerprint}`}
              className="btn btn-ghost btn-sm"
              disabled={!!actionLoading[row.fingerprint]}
              onClick={() => doRemoveTrust(row.fingerprint)}
            >
              {actionLoading[row.fingerprint] === 'remove'
                ? <span className="spinner" style={{width:12,height:12}} />
                : <Trash2 size={12} />}
              Remove Trust
            </button>,
            <button
              key="block"
              id={`block-trusted-${row.fingerprint}`}
              className="btn btn-danger btn-sm"
              disabled={!!actionLoading[row.fingerprint]}
              onClick={() => doBlock(row.fingerprint)}
            >
              {actionLoading[row.fingerprint] === 'block'
                ? <span className="spinner" style={{width:12,height:12}} />
                : <Ban size={12} />}
              Block
            </button>,
          ]}
        />
      </div>
    </div>
  );
}
