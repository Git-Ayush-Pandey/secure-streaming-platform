import React from 'react';
import { Routes, Route } from 'react-router-dom';

import { AppProvider } from './context/AppContext';
import Sidebar from './components/Sidebar';
import ServerStatusBar from './components/ServerStatusBar';
import PendingModal from './components/PendingModal';

import DashboardHome     from './pages/DashboardHome';
import ConnectedDevices  from './pages/ConnectedDevices';
import TrustedDevices    from './pages/TrustedDevices';
import BlockedDevices    from './pages/BlockedDevices';
import RecentConnections from './pages/RecentConnections';
import RejectedDevices   from './pages/RejectedDevices';
import StreamConfig      from './pages/StreamConfig';
import SecurityMonitor  from './pages/SecurityMonitor';
import Logs              from './pages/Logs';

export default function App() {
  return (
    <AppProvider>
      <div className="app-shell">
        <Sidebar />
        <div className="app-main">
          <ServerStatusBar />
          <main className="page-content">
            <Routes>
              <Route path="/"          element={<DashboardHome />} />
              <Route path="/connected" element={<ConnectedDevices />} />
              <Route path="/trusted"   element={<TrustedDevices />} />
              <Route path="/blocked"   element={<BlockedDevices />} />
              <Route path="/recent"    element={<RecentConnections />} />
              <Route path="/rejected"  element={<RejectedDevices />} />
              <Route path="/stream"    element={<StreamConfig />} />
              <Route path="/security"  element={<SecurityMonitor />} />
              <Route path="/logs"      element={<Logs />} />
            </Routes>
          </main>
        </div>
      </div>

      {/* Global pending device modal — auto-shows when WS fires pending_request */}
      <PendingModal />
    </AppProvider>
  );
}
