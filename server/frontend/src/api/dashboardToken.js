/**
 * Dashboard auth token storage (F1).
 *
 * The backend mints a single bearer token on first startup and prints a
 * bootstrap URL of the form:
 *
 *   http://127.0.0.1:5173/?token=<token>
 *
 * Visiting that URL once stores the token in localStorage so subsequent
 * page loads don't need the query parameter again. This mirrors the
 * Jupyter notebook token-URL pattern the backend's own comments reference.
 *
 * Every authenticated fetch (api.js) and the dashboard WebSocket
 * (useDashboardSocket.js) read the token via getDashboardToken().
 */

const STORAGE_KEY = 'dashboard_token';

/**
 * On first import, check the URL for a ?token=... query parameter. If
 * present, persist it to localStorage and strip it from the visible URL
 * (so the token doesn't linger in browser history / get shared via a
 * copy-pasted link).
 */
function captureTokenFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    if (!urlToken) return;

    localStorage.setItem(STORAGE_KEY, urlToken);

    params.delete('token');
    const newSearch = params.toString();
    const newUrl =
        window.location.pathname +
        (newSearch ? `?${newSearch}` : '') +
        window.location.hash;
    window.history.replaceState({}, document.title, newUrl);
}

captureTokenFromUrl();

export function getDashboardToken() {
    return localStorage.getItem(STORAGE_KEY) || null;
}

export function setDashboardToken(token) {
    if (token) {
        localStorage.setItem(STORAGE_KEY, token);
    } else {
        localStorage.removeItem(STORAGE_KEY);
    }
}

export function clearDashboardToken() {
    localStorage.removeItem(STORAGE_KEY);
}