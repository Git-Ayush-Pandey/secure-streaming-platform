#!/usr/bin/env python3
"""
Drone Stream Server — Launch Script.

Starts TWO uvicorn listeners against the same FastAPI app:

  1. Dashboard/admin listener — loopback only (127.0.0.1 / ::1).
     Serves the React dashboard's API, /ws/dashboard, /docs (if DEBUG),
     and every /api/* admin route. This is the ONLY listener that drives
     the app's lifespan (startup/shutdown) — key loading, UDP socket
     bind, capture service, session GC, etc. all happen here exactly as
     in the single-listener version of this file.

  2. Auth/streaming listener — LAN-reachable by default (0.0.0.0), but
     wrapped in LANSurfaceFilter (see backend/main.py) so only /ws/auth
     and /health are dispatched; every other path is rejected with a
     403/WS-close before Starlette's router ever sees it. lifespan="off"
     on this listener — it reuses the state the first listener already
     initialized; it must NOT re-run startup (that would re-bind the UDP
     socket, double-start the capture loop, etc.).

This is what lets a Windows client on another LAN machine reach
ws://<server-lan-ip>:<AUTH_BIND_PORT>/ws/auth while the dashboard and
every admin endpoint remain provably unreachable from anywhere but
localhost — enforced at the socket/listener level, not just by the
per-route _localhost_only() checks (which still run too, as defense in
depth).

Usage:
    python run.py                   # dashboard: 127.0.0.1:8766, auth: 0.0.0.0:8766
    python run.py --port 8000       # explicit dashboard port
    python run.py --auth-port 9000  # auth listener on a different port
    python run.py --reload          # dev mode with auto-reload (dashboard listener only)

Backward compatibility: if you don't set AUTH_BIND_HOST/AUTH_BIND_PORT
(or pass --auth-host/--auth-port), the auth listener defaults to
0.0.0.0:<dashboard-port> — same port number the client already expects
from before this change, just now also reachable from the LAN. Running
fully single-machine (server + client on the same box) keeps working
unmodified; SERVER_IP=127.0.0.1 on the client still resolves correctly
against the auth listener's 0.0.0.0 bind.
"""
from __future__ import annotations

import argparse
import asyncio
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

_DEFAULT_AUTH_HOST = os.getenv("AUTH_BIND_HOST", "0.0.0.0")
_DEFAULT_AUTH_PORT_RAW = os.getenv("AUTH_BIND_PORT")  # may be unset


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
    # Auth listener MUST use a different port number than the dashboard —
    # 0.0.0.0:N and 127.0.0.1:N cannot both be bound (0.0.0.0 is a
    # wildcard that already covers 127.0.0.1 at that port). Defaults to
    # dashboard_port + 1 unless explicitly overridden via AUTH_BIND_PORT
    # or --auth-port. Set WindowsClient/.env's AUTH_PORT to match.
    cfg_auth_port = int(_DEFAULT_AUTH_PORT_RAW) if _DEFAULT_AUTH_PORT_RAW else cfg_port + 1

    parser = argparse.ArgumentParser(description="Start the Drone Stream Server")
    parser.add_argument("--host", default=cfg_host,
                        help=f"Dashboard bind host, MUST be loopback (default: {cfg_host})")
    parser.add_argument("--port", type=int, default=cfg_port,
                        help=f"Dashboard bind port (default: {cfg_port})")
    parser.add_argument("--auth-host", default=_DEFAULT_AUTH_HOST,
                        help=f"Auth/streaming listener bind host (default: {_DEFAULT_AUTH_HOST}). "
                             f"Use 0.0.0.0 for LAN clients, 127.0.0.1 to keep everything local-only.")
    parser.add_argument("--auth-port", type=int, default=cfg_auth_port,
                        help=f"Auth/streaming listener bind port (default: {cfg_auth_port})")
    parser.add_argument("--no-auth-listener", action="store_true",
                        help="Disable the second (auth/LAN) listener entirely — "
                             "single-listener mode identical to versions before the LAN split. "
                             "Remote clients will not be able to authenticate.")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload for development (dashboard listener only)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of uvicorn worker processes for the dashboard listener (default: 1)")
    args = parser.parse_args()

    # Security: reject any host that is not a loopback address for the
    # DASHBOARD listener specifically. This check is unchanged from before
    # the LAN split and is the most important invariant in this file —
    # the dashboard/admin surface must never be bound to an externally
    # reachable interface, regardless of what the auth listener does.
    _ALLOWED_DASHBOARD_HOSTS = {"127.0.0.1", "::1", "localhost"}
    if args.host not in _ALLOWED_DASHBOARD_HOSTS:
        print(
            f"[run.py] ERROR: --host '{args.host}' is not allowed for the dashboard.\n"
            f"  The dashboard UI and admin API must only bind to a loopback address "
            f"(127.0.0.1 / ::1).\n"
            f"  Remote clients use the auth/UDP listeners (--auth-host / --auth-port), "
            f"not the dashboard port.\n"
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

    # uvicorn's --reload and multi-worker modes hand the whole process over
    # to a ChangeReload/Multiprocess supervisor that owns its own run loop
    # and re-execs `server.run()` in a subprocess. That's incompatible with
    # running a second uvicorn.Server concurrently via asyncio.gather() in
    # this same process. Rather than silently dropping the auth listener
    # (which would quietly break remote clients) or silently dropping
    # --reload (surprising for a dev workflow), fail loudly and tell the
    # operator their two options up front, before printing a banner that
    # would otherwise misdescribe what's about to start.
    if (args.reload or args.workers > 1) and not args.no_auth_listener:
        print(
            "[run.py] ERROR: --reload and --workers > 1 are not compatible with the "
            "LAN auth listener in this single-process launcher.\n"
            "  Use ONE of:\n"
            "    python run.py --reload                     (dev mode, loopback-only, "
            "no LAN clients)\n"
            "    python run.py --no-auth-listener --reload  (same, explicit)\n"
            "    python run.py                              (LAN clients can authenticate, "
            "no --reload)\n",
            file=sys.stderr,
        )
        sys.exit(1)

    single_listener_mode = args.no_auth_listener or args.reload or args.workers > 1

    # A socket bound to 0.0.0.0:N and one bound to 127.0.0.1:N cannot
    # coexist (0.0.0.0 is a wildcard covering 127.0.0.1 at that port).
    # Fail clearly here instead of letting uvicorn raise an
    # "Address already in use" traceback that doesn't explain why.
    if not single_listener_mode and args.port == args.auth_port:
        print(
            f"[run.py] ERROR: dashboard port ({args.port}) and auth port "
            f"({args.auth_port}) must be different.\n"
            f"  A socket bound to 0.0.0.0:{args.auth_port} and one bound to "
            f"127.0.0.1:{args.port} cannot share the same port number.\n"
            f"  Pick a different --auth-port (or set AUTH_BIND_PORT), e.g.:\n"
            f"    python run.py --auth-port {args.port + 1}\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting Drone Stream Server")
    print(f"  Dashboard/admin (loopback only): http://{args.host}:{args.port}")
    if single_listener_mode:
        reason = "--reload/--workers" if (args.reload or args.workers > 1) else "--no-auth-listener"
        print(f"  Auth/streaming listener: DISABLED ({reason}) — "
              f"remote clients cannot authenticate")
    else:
        print(f"  Auth/streaming (LAN-reachable):  ws://{args.auth_host}:{args.auth_port}/ws/auth")
        print(f"    -> only /ws/auth and /health are reachable on this listener;")
        print(f"       dashboard and admin APIs are NOT served here (LANSurfaceFilter).")
    print(f"  Reload: {args.reload} | Workers: {args.workers}")
    print(f"  Frontend should connect to: http://127.0.0.1:{args.port}")
    print()

    dashboard_config = uvicorn.Config(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info",
        lifespan="on",  # drives real startup/shutdown — see backend/main.py lifespan()
    )

    if single_listener_mode:
        # Identical behavior to versions of this script before the LAN
        # split. Used when the LAN auth listener is explicitly disabled
        # (--no-auth-listener), or implicitly when --reload/--workers makes
        # the dual-listener approach unavailable (validated above).
        uvicorn.Server(dashboard_config).run()
        return

    auth_config = uvicorn.Config(
        "backend.main:lan_app",
        host=args.auth_host,
        port=args.auth_port,
        log_level="info",
        lifespan="off",  # IMPORTANT: must not re-run startup — see module docstring
    )

    dashboard_server = uvicorn.Server(dashboard_config)
    auth_server = uvicorn.Server(auth_config)

    async def _run_both() -> None:
        await asyncio.gather(
            dashboard_server.serve(),
            auth_server.serve(),
        )

    try:
        asyncio.run(_run_both())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
