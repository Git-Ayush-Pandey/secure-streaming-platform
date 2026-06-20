import React from 'react';
import { Routes, Route } from 'react-router-dom';

import { useApp } from './context/AppContext';
import Sidebar from './components/Sidebar';
import ServerStatusBar from './components/ServerStatusBar';
import PendingModal from './components/PendingModal';
import AuthGate from './components/AuthGate';

import DashboardHome from './pages/DashboardHome';
import ConnectedDevices from './pages/ConnectedDevices';
import TrustedDevices from './pages/TrustedDevices';
import BlockedDevices from './pages/BlockedDevices';
import RecentConnections from './pages/RecentConnections';
import RejectedDevices from './pages/RejectedDevices';
import StreamConfig from './pages/StreamConfig';
import SecurityMonitor from './pages/SecurityMonitor';
import Logs from './pages/Logs';

export default function AppShell() {
    const { needsAuth } = useApp();

    // F1: every page below this point assumes an authenticated dashboard
    // token. Rather than have each page fail its own API calls with 401s,
    // gate the whole dashboard behind AuthGate until a valid token is
    // stored (see api/dashboardToken.js + AppContext's needsAuth state).
    if (needsAuth) {
        return <AuthGate />;
    }

    return (
        <>
            <div className="app-shell">
                <Sidebar />
                <div className="app-main">
                    <ServerStatusBar />
                    <main className="page-content">
                        <Routes>
                            <Route path="/" element={<DashboardHome />} />
                            <Route path="/connected" element={<ConnectedDevices />} />
                            <Route path="/trusted" element={<TrustedDevices />} />
                            <Route path="/blocked" element={<BlockedDevices />} />
                            <Route path="/recent" element={<RecentConnections />} />
                            <Route path="/rejected" element={<RejectedDevices />} />
                            <Route path="/stream" element={<StreamConfig />} />
                            <Route path="/security" element={<SecurityMonitor />} />
                            <Route path="/logs" element={<Logs />} />
                        </Routes>
                    </main>
                </div>
            </div>

            {/* Global pending device modal — auto-shows when WS fires pending_request */}
            <PendingModal />
        </>
    );
}