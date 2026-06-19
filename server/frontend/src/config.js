export const CONFIG = {
  API_URL: import.meta.env.VITE_API_URL,
  WS_URL: import.meta.env.VITE_WS_URL,

  APP_NAME:
    import.meta.env.VITE_APP_NAME ?? 'DroneStream',

  APP_VERSION:
    import.meta.env.VITE_APP_VERSION ?? '2.1.0',

  POLL_INTERVAL:
    Number(import.meta.env.VITE_POLL_INTERVAL ?? 3000),

  LOG_REFRESH_INTERVAL:
    Number(import.meta.env.VITE_LOG_REFRESH_INTERVAL ?? 5000),

  DEVICE_REFRESH_INTERVAL:
    Number(import.meta.env.VITE_DEVICE_REFRESH_INTERVAL ?? 15000),

  WS_RECONNECT_INTERVAL:
    Number(import.meta.env.VITE_WS_RECONNECT_INTERVAL ?? 3000),

  DEV_HOST:
    import.meta.env.VITE_DEV_HOST ?? '127.0.0.1',

  DEV_PORT:
    Number(import.meta.env.VITE_DEV_PORT ?? 5173),
};