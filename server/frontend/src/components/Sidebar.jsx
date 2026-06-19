import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Monitor, Shield, Ban, Clock, XCircle,
  Settings, FileText, Radio, Wifi, AlertTriangle, ShieldAlert
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import { CONFIG } from '../config';

const navItems = [
  { to: '/',          icon: Monitor,  label: 'Overview',           section: 'dashboard' },
  { to: '/connected', icon: Wifi,     label: 'Connected Devices',  section: 'devices' },
  { to: '/trusted',   icon: Shield,   label: 'Trusted Devices',    section: 'devices' },
  { to: '/blocked',   icon: Ban,      label: 'Blocked Devices',    section: 'devices' },
  { to: '/recent',    icon: Clock,    label: 'Recent Connections', section: 'history' },
  { to: '/rejected',  icon: XCircle,  label: 'Rejected',           section: 'history' },
  { to: '/stream',    icon: Settings,     label: 'Capture Config',   section: 'system' },
  { to: '/security',  icon: ShieldAlert,  label: 'Security Monitor', section: 'system' },
  { to: '/logs',      icon: FileText, label: 'Event Logs',         section: 'system' },
];

export default function Sidebar() {
  const { pendingRequests, serverInfo } = useApp();
  const pendingCount = pendingRequests.length;

  const isOnline  = !!serverInfo;
  const udpPort   = serverInfo?.stream?.udp_port ?? serverInfo?.config?.server?.port ?? null;
  const udpActive = serverInfo?.stream?.running;

  return (
    <aside className="sidebar">
      {/* Logo */}
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">
          <div className="sidebar-logo-icon">
            <Radio size={18} color="#000" />
          </div>
          <div className="sidebar-logo-text">
            <strong>{CONFIG.APP_NAME}</strong>
            <span>Secure Feed Server</span>
          </div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {/* Pending alert badge */}
        {pendingCount > 0 && (
          <NavLink
            to="/"
            className="nav-item"
            style={{
              background:   'rgba(255,153,51,0.08)',
              borderColor:  'rgba(255,153,51,0.25)',
              marginBottom: 8,
              border:       '1px solid',
            }}
          >
            <AlertTriangle size={15} color="var(--accent-orange)" />
            <span style={{ color: 'var(--accent-orange)', fontSize: 12 }}>
              {pendingCount} pending approval
            </span>
          </NavLink>
        )}

        <div className="sidebar-section-label">Dashboard</div>
        {navItems.filter(n => n.section === 'dashboard').map(n => (
          <NavItem key={n.to} {...n} />
        ))}

        <div className="sidebar-section-label">Devices</div>
        {navItems.filter(n => n.section === 'devices').map(n => (
          <NavItem
            key={n.to}
            {...n}
            pendingCount={n.to === '/connected' ? pendingCount : 0}
          />
        ))}

        <div className="sidebar-section-label">History</div>
        {navItems.filter(n => n.section === 'history').map(n => (
          <NavItem key={n.to} {...n} />
        ))}

        <div className="sidebar-section-label">System</div>
        {navItems.filter(n => n.section === 'system').map(n => (
          <NavItem key={n.to} {...n} />
        ))}
      </nav>

      {/* Footer: server status + UDP info */}
      <div className="sidebar-footer">
        <div style={{ marginBottom: 5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--text-muted)' }}>Server</span>
          <span style={{
            color:      isOnline ? 'var(--accent-green)' : 'var(--accent-red)',
            fontWeight: 600,
            fontSize:   11,
          }}>
            {isOnline ? 'Online' : 'Offline'}
          </span>
        </div>

        {udpPort && (
          <div style={{ marginBottom: 5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-muted)' }}>UDP Stream</span>
            <span style={{
              fontFamily: 'JetBrains Mono',
              fontSize:   10,
              color:      udpActive ? 'var(--accent-green)' : 'var(--text-muted)',
            }}>
              :{udpPort} {udpActive ? '●' : '○'}
            </span>
          </div>
        )}

        <div style={{
          fontFamily: 'JetBrains Mono',
          fontSize:   10,
          color:      'var(--text-muted)',
          wordBreak:  'break-all',
          marginTop:  4,
        }}>
          {serverInfo?.server_fingerprint?.slice(0, 20)}…
        </div>
      </div>
    </aside>
  );
}

function NavItem({ to, icon: Icon, label, pendingCount = 0 }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
    >
      <Icon size={15} />
      {label}
      {pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
    </NavLink>
  );
}
