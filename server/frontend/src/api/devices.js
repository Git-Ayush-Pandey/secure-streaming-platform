import { apiFetch } from './api';

// Connected
export const getConnected = () => apiFetch('/api/devices/connected');

// Pending
export const getPending       = ()          => apiFetch('/api/devices/pending');
export const approvePending   = (fp)        => apiFetch(`/api/devices/pending/${fp}/approve`,    { method: 'POST' });
export const allowOncePending = (fp)        => apiFetch(`/api/devices/pending/${fp}/allow_once`, { method: 'POST' });
export const rejectPending    = (fp)        => apiFetch(`/api/devices/pending/${fp}/reject`,     { method: 'POST' });
export const blockPending     = (fp)        => apiFetch(`/api/devices/pending/${fp}/block`,      { method: 'POST' });
export const removeDevice = (fp) => apiFetch(`/api/devices/${fp}/disconnect`, { method: 'POST' });
// Trusted
export const getTrusted    = (limit = 10, offset = 0) => apiFetch(`/api/devices/trusted?limit=${limit}&offset=${offset}`);
export const removeTrust   = (fp)                     => apiFetch(`/api/devices/trusted/${fp}`,       { method: 'DELETE' });
export const blockTrusted  = (fp)                     => apiFetch(`/api/devices/trusted/${fp}/block`, { method: 'POST' });

// Blocked
export const getBlocked    = (limit = 10, offset = 0) => apiFetch(`/api/devices/blocked?limit=${limit}&offset=${offset}`);
export const unblockDevice = (fp)                     => apiFetch(`/api/devices/blocked/${fp}/unblock`, { method: 'POST' });
export const trustBlocked  = (fp)                     => apiFetch(`/api/devices/blocked/${fp}/trust`,   { method: 'POST' });

// Recent / Rejected
export const getRecent   = (limit = 10, offset = 0) => apiFetch(`/api/devices/recent?limit=${limit}&offset=${offset}`);
export const getRejected = (limit = 10, offset = 0) => apiFetch(`/api/devices/rejected?limit=${limit}&offset=${offset}`);
