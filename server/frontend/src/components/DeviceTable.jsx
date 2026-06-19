import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

export default function DeviceTable({ columns, rows, loading, onLoadMore, hasMore, actions }) {
  if (loading && !rows.length) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
        <span className="spinner" />
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">📭</div>
        <p>No records found.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map(c => <th key={c.key}>{c.label}</th>)}
              {actions && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {columns.map(c => (
                  <td key={c.key} className={c.className || ''}>
                    {c.render ? c.render(row) : (row[c.key] ?? '—')}
                  </td>
                ))}
                {actions && (
                  <td>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {actions(row)}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="load-more-row">
          <button className="btn btn-ghost btn-sm" onClick={onLoadMore} disabled={loading}>
            {loading ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <ChevronDown size={14} />}
            Load More
          </button>
        </div>
      )}
    </div>
  );
}
