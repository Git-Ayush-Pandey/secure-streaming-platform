import React from 'react';

export default function StatCard({ label, value, sub, icon, color = 'var(--accent-cyan)' }) {
  return (
    <div className="stat-card" style={{ '--accent-color': color }}>
      <div className="stat-card-icon">{icon}</div>
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value">{value ?? '—'}</div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  );
}
