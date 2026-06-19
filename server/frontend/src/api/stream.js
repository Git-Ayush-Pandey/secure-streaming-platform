import { apiFetch } from './api';

export const startStream     = ()     => apiFetch('/api/stream/start', { method: 'POST' });
export const stopStream      = ()     => apiFetch('/api/stream/stop',  { method: 'POST' });
export const configureStream = (body) => apiFetch('/api/stream/configure', {
  method: 'POST',
  body: JSON.stringify(body),
});
