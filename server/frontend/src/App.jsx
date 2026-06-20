import React from 'react';

import { AppProvider } from './context/AppContext';
import AppShell from './AppShell';

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}