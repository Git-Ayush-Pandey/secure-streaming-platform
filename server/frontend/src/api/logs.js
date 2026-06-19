import { apiFetch } from './api';

export const getLogs = (limit = 200) => apiFetch(`/api/logs?limit=${limit}`);
