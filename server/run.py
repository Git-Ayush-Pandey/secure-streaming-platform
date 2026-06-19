#!/usr/bin/env python3
"""
Drone Stream Server — Launch Script.

Reads dashboard_host / dashboard_port from server_config.json (if it
exists) and starts uvicorn on that address. Falls back to 127.0.0.1:8000
which matches the frontend's hardcoded BASE URL.

Usage:
    python run.py                   # default: 127.0.0.1:8000
    python run.py --port 8000       # explicit port
    python run.py --reload          # dev mode with auto-reload
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(
    Path(__file__).parent / "backend" / ".env"
)
# ── Resolve config path without importing the full backend ────────────────────
_HERE      = Path(__file__).parent
_CFG_FILE  = _HERE / "backend" / "data" / "config" / "server_config.json"

import os

_DEFAULT_HOST = os.getenv(
    "SERVER_HOST",
    "127.0.0.1"
)

_DEFAULT_PORT = int(
    os.getenv(
        "SERVER_PORT",
        "8766"
    )
)

def _load_dashboard_addr() -> tuple[str, int]:
    """Read dashboard_host / dashboard_port from persisted config, if present."""
    if not _CFG_FILE.exists():
        return _DEFAULT_HOST, _DEFAULT_PORT
    try:
        cfg  = json.loads(_CFG_FILE.read_text())
        srv  = cfg.get("server", {})
        host = srv.get("dashboard_host", _DEFAULT_HOST)
        port = int(srv.get("dashboard_port", _DEFAULT_PORT))
        return host, port
    except Exception as exc:
        print(f"[run.py] Warning: could not read {_CFG_FILE}: {exc}", file=sys.stderr)
        return _DEFAULT_HOST, _DEFAULT_PORT


def main() -> None:
    cfg_host, cfg_port = _load_dashboard_addr()

    parser = argparse.ArgumentParser(description="Start the Drone Stream Server dashboard")
    parser.add_argument("--host", default=cfg_host,
                        help=f"Dashboard bind host (default: {cfg_host})")
    parser.add_argument("--port", type=int, default=cfg_port,
                        help=f"Dashboard bind port (default: {cfg_port})")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload for development")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of uvicorn worker processes (default: 1)")
    args = parser.parse_args()

    # Security: reject any host that is not a loopback address.
    # The dashboard must never be bound to an externally reachable interface.
    _ALLOWED_DASHBOARD_HOSTS = {"127.0.0.1", "::1", "localhost"}
    if args.host not in _ALLOWED_DASHBOARD_HOSTS:
        print(
            f"[run.py] ERROR: --host '{args.host}' is not allowed for the dashboard.\n"
            f"  The dashboard UI must only bind to a loopback address "
            f"(127.0.0.1 / ::1).\n"
            f"  Remote clients use the UDP stream port, not the dashboard port.\n"
            f"  Refused to start to protect the admin interface.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is not installed. Run: pip install -r backend/requirements.txt",
              file=sys.stderr)
        sys.exit(1)

    print(f"Starting Drone Stream Server dashboard on http://{args.host}:{args.port}")
    print(f"  Reload: {args.reload} | Workers: {args.workers}")
    print(f"  Frontend should connect to: http://127.0.0.1:{args.port}")
    print()

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info",
    )


if __name__ == "__main__":
    main()