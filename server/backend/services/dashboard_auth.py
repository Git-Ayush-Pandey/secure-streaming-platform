"""
Dashboard authentication — lightweight bearer-token auth for the local
admin API, plus Origin allow-listing for state-changing requests.

Hardening: F1 (dashboard authentication), F2 (CSRF protection).

Design goals (kept deliberately simple — no accounts, no passwords, no
external auth provider, no new dependency):
  - A single, randomly generated token is created on first run and
    persisted to disk with owner-only permissions (same pattern already
    used for the Ed25519 key passphrase in crypto_service.py).
  - The token must be presented either as `Authorization: Bearer <token>`
    (used by the dashboard's fetch calls) or as a `?token=` query
    parameter (used for the WebSocket connection and for the one-time
    bootstrap link the server prints at startup — this mirrors the
    well-known Jupyter notebook token-URL pattern).
  - Because the token must be supplied via a custom header or query
    parameter that a third-party page cannot set on a simple
    cross-origin <form> submission, and because our CORS policy still
    only allows reading responses from known dashboard origins, this
    closes the "any local process / cross-site request can drive the
    admin API" gap without adding a login system.
  - The existing localhost-only source-IP check is kept as defense in
    depth; this module adds to it, it does not replace it.
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, Request, WebSocket

from .. import config as cfg

_TOKEN_FILE_NAME = ".dashboard_token"
_TOKEN_CACHE: str | None = None


def _token_path() -> Path:
    return cfg.CONFIG_DIR / _TOKEN_FILE_NAME


def ensure_dashboard_token() -> str:
    """
    Load the persisted dashboard token, generating one on first run.
    Idempotent — safe to call on every startup.
    """
    path = _token_path()
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass  # Windows: best-effort, same fallback as crypto_service.py
    return token


def get_dashboard_token() -> str:
    """Cached accessor — avoids a disk read on every request."""
    global _TOKEN_CACHE
    if _TOKEN_CACHE is None:
        _TOKEN_CACHE = ensure_dashboard_token()
    return _TOKEN_CACHE


def _extract_token(auth_header: str | None, query_token: str | None) -> str | None:
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return query_token


def _token_matches(candidate: str | None) -> bool:
    if not candidate:
        return False
    return secrets.compare_digest(candidate, get_dashboard_token())


def _origin_allowed(origin: str | None, allowed_origins: Iterable[str]) -> bool:
    if origin is None:
        # Non-browser clients (curl, the operator's own scripts) don't send
        # an Origin header at all — they're already required to know the
        # bearer token, so we don't penalize them for the header's absence.
        return True
    return origin in set(allowed_origins)


def require_dashboard_auth(request: Request) -> None:
    """
    Combined guard for HTTP admin routes:
      1. Source IP must be localhost (unchanged behaviour).
      2. A valid bearer token must be present (F1).
      3. For state-changing methods, if an Origin header is present it
         must be in the configured CORS allow-list (F2).
    Raises HTTPException on failure; callers use this exactly like the
    previous `_localhost_only` check.
    """
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(
            status_code=403,
            detail="Dashboard API is accessible from localhost only",
        )

    token = _extract_token(
        request.headers.get("authorization"),
        request.query_params.get("token"),
    )
    if not _token_matches(token):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid dashboard token",
        )

    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        from ..settings import CORS_ORIGINS
        origin = request.headers.get("origin")
        if not _origin_allowed(origin, CORS_ORIGINS):
            raise HTTPException(status_code=403, detail="Origin not allowed")


def dashboard_ws_token_valid(ws: WebSocket) -> bool:
    """Token check for the /ws/dashboard handshake (query parameter only —
    browsers cannot set custom headers on a WebSocket upgrade request)."""
    return _token_matches(ws.query_params.get("token"))


def actor_id_from_request(request: Request) -> str:
    """
    F10: a short, stable, non-secret identifier derived from the caller's
    dashboard token, suitable for audit-log attribution.

    This is a single-operator tool with one shared token rather than a
    multi-user account system, so true per-user identity isn't available —
    but hashing the token still lets the audit log distinguish "the
    dashboard" from any other localhost-originating caller, and lets a
    token rotation show up as a new actor id in the log trail. The hash is
    one-way, so it never leaks the token itself into log files.
    """
    import hashlib
    token = _extract_token(
        request.headers.get("authorization"),
        request.query_params.get("token"),
    )
    if not token:
        return "unknown"
    return "dash-" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]