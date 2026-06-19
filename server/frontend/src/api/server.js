import { apiFetch } from './api';

export const getServerInfo = () => apiFetch('/api/server/info');
export const getHealth     = () => apiFetch('/health');
