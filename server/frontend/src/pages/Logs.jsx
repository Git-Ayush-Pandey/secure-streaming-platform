import React, { useState, useCallback } from 'react';
import { FileText, RefreshCw } from 'lucide-react';
import LogViewer from '../components/LogViewer';
import { usePolling } from '../hooks/usePolling';
import { getLogs } from '../api/logs';
import { CONFIG } from '../config';

export default function Logs() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [limit, setLimit] = useState(200);

  const fetch = useCallback(async () => {
    try {
      const { logs: l } = await getLogs(limit);
      setLogs([...(l || [])].reverse()); // newest last for auto-scroll
    } catch (_) {}
    finally { setLoading(false); }
  }, [limit]);

  usePolling(
      fetch,
      CONFIG.LOG_REFRESH_INTERVAL,
      [limit]
  );
  return (
    <div>
      <div className="flex-between mb-20">
        <div>
          <h1 className="page-title">Event Logs</h1>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Real-time server event stream — auto-refresh enabled</p>
        </div>
        <div className="flex gap-8">
          <select
            id="log-limit-select"
            className="form-select"
            style={{ width: 140 }}
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
          >
            <option value={50}>Last 50</option>
            <option value={100}>Last 100</option>
            <option value={200}>Last 200</option>
            <option value={500}>Last 500</option>
          </select>
          <button className="btn btn-ghost btn-sm" onClick={fetch}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div className="card-title" style={{ margin: 0 }}>
            <FileText size={14} />
            Server Events
            <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 12 }}>
              {logs.length} entries
            </span>
          </div>
        </div>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
            <span className="spinner" />
          </div>
        ) : (
          <LogViewer logs={logs} autoScroll />
        )}
      </div>
    </div>
  );
}
