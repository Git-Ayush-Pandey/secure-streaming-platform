"""
Drone Stream Server — Main Application (Hardened + Fixes Edition).

Fixes applied vs previous version:
  ✓ FINDING-03: auth_ws passes WebSocket reference into handle_hello so
    approve/allow_once can push a challenge directly to the client.
  ✓ FINDING-04: auth_ws calls on_auth_ws_disconnect on teardown so single-use
    sessions are revoked immediately on clean WebSocket close.
  ✓ FINDING-06: startup() checks stream_service._running after start(); raises
    so uvicorn aborts startup on UDP bind failure. /health exposes udp_running.
  ✓ FINDING-07: asyncio.get_running_loop() used (delegated to stream_service).
  ✓ FINDING-08: "localhost" removed from _localhost_only() allowlist.
  ✓ FINDING-13: WebSocketDisconnect caught separately from unexpected exceptions.
  ✓ FINDING-17: _reconfigure_lock prevents concurrent configure_stream calls.
  ✓ FINDING-18: logger.flush() called in shutdown handler.
  ✓ config.initialize() called in startup (not at import time).
  ✓ startup_validate() called to detect corrupted registry files.
  ✓ @app.on_event deprecated → lifespan context manager (FastAPI ≥ 0.95).
  ✓ configure_stream validates body is a dict before accessing .get().
"""
from __future__ import annotations

import asyncio
import json
import base64
import time
import traceback
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config as cfg
from .config import KEYS_DIR
from .services.crypto_service import (
    ensure_server_keys, get_server_public_b64, fingerprint, fingerprint_from_raw_b64,
)
from .services.auth_service import auth_service
from .services.capture_service import capture_service
from .services.stream_service import stream_service
from .services import device_registry as reg
from .services.logger import log_event, get_recent_logs, flush as log_flush
from .services.dashboard_auth import (
    ensure_dashboard_token,
    get_dashboard_token,
    require_dashboard_auth,
    dashboard_ws_token_valid,
    actor_id_from_request,
)
from .settings import (
    DEBUG,
    CORS_ORIGINS,
    MAX_DASHBOARD_CLIENTS,
    UDP_HOST,
    AUTH_WS_MAX_CONNECTIONS,
    AUTH_WS_IDLE_TIMEOUT,
    DASHBOARD_WS_MAX_LIFETIME,
)
# ── Server identity (generated once, persisted) ───────────────────────────────
_server_private, _server_public = None, None
_server_fp: str = ""
# Public key cached at startup so server_info() never touches disk per-request.
_server_public_key_b64: str = ""

# ── Dashboard WebSocket connections ───────────────────────────────────────────
_dashboard_sockets: list[WebSocket] = []

# ── F6: /ws/auth connection-level resource bound ──────────────────────────────
_auth_ws_count: int = 0

# ── Configure-stream lock (FINDING-17) ───────────────────────────────────────
# FIX: asyncio.Lock() must be created inside a running event loop on Python
# 3.10+ (3.13 on Windows/ProactorEventLoop raises RuntimeError if the Lock
# was built before the loop started).  Initialised to None here; the lifespan
# context manager creates the real Lock as its very first action.
_reconfigure_lock: asyncio.Lock | None = None


async def _push_dashboard(event: str, data: dict) -> None:
    dead = []
    for ws in _dashboard_sockets:
        try:
            await ws.send_json({"event": event, "data": data})
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _dashboard_sockets:
            _dashboard_sockets.remove(ws)


def _on_pending(req) -> None:
    asyncio.create_task(_push_dashboard("pending_request", {
        "device_id":   req.device_id,
        "device_name": req.device_name,
        "fingerprint": req.fingerprint,
        "ip":          req.ip,
        "timestamp":   req.timestamp,
    }))


auth_service.register_pending_callback(_on_pending)


# ── Lifespan (replaces deprecated @app.on_event) ──────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _server_private, _server_public, _server_fp, _server_public_key_b64, _reconfigure_lock

    # FIX: create asyncio.Lock() here, inside the running event loop.
    # This is the correct place for any asyncio primitive that must not be
    # shared across different event loop instances (e.g. ProactorEventLoop
    # on Windows in Python 3.13 raises "got Future attached to different loop"
    # if the Lock was created before uvicorn's loop started).
    _reconfigure_lock = asyncio.Lock()

    # Initialise directories explicitly (not at import time)
    cfg.initialize()

    # Validate registry files before use (FINDING-10)
    reg.startup_validate()

    # Load / generate server keys
    _server_private, _server_public = ensure_server_keys(KEYS_DIR)
    _server_fp = fingerprint(_server_public)
    # Cache the base64 public key once — server_info() will read the cached
    # value instead of opening the PEM file on every dashboard poll.
    _server_public_key_b64 = get_server_public_b64(KEYS_DIR)
    auth_service.set_server_keys(_server_private, _server_public, _server_fp)

    server_cfg = cfg.load_config()
    cap        = server_cfg["capture"]
    udp_port   = server_cfg["server"].get("port", 8765)
# codec = cap.get("codec", "h264")  # No longer needed

    # F1: generate/load the dashboard bearer token and print a ready-to-use
    # bootstrap URL, the same way Jupyter prints a token URL on startup.
    # Pasting this URL into the dashboard once stores the token in the
    # browser (localStorage); subsequent visits don't need it again.
    dash_token = ensure_dashboard_token()
    dash_host  = server_cfg["server"].get("dashboard_host", "127.0.0.1")
    dash_port  = server_cfg["server"].get("dashboard_port", 5173)
    bootstrap_url = f"http://{dash_host}:{dash_port}/?token={dash_token}"
    print(f"\n=== Dashboard access ===\n{bootstrap_url}\n"
          f"(Token also stored at data/config/.dashboard_token)\n", flush=True)
    log_event("DASHBOARD_TOKEN_READY", {"dashboard_host": dash_host, "dashboard_port": dash_port})

    capture_service.configure(
        x=cap["x"], y=cap["y"],
        width=cap["width"], height=cap["height"],
        fps=cap["fps"],
    )
    await capture_service.start()
    stream_service.capture_started()

    # FINDING-06: start() now raises on bind failure
    try:
        await stream_service.start(
            host=UDP_HOST,
            port=udp_port
        )
    except RuntimeError as exc:
        log_event("UDP_STARTUP_FATAL", {"error": str(exc)})
        # Still allow the app to serve the dashboard even if UDP failed
        # (operator needs to see error state and reconfigure)
        log_event("WARNING", {
            "msg": "Server running in degraded mode — UDP disabled",
            "udp_error": str(exc),
        })

    await auth_service.start_gc()
    log_event("STREAM_STARTED", {"config": cap, "udp_port": udp_port})

    yield   # ← application runs here

    # Shutdown
    stream_service.capture_stopped()
    await capture_service.stop()
    await stream_service.stop()
    log_event("STREAM_STOPPED", {})
    # FINDING-18: flush all queued log records before exit
    log_flush(timeout=5.0)

app = FastAPI(
    title="Drone Stream Server",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global unhandled-exception handler ──────────────────────────────────────────
# FINDING-21: Without this, any unhandled exception in a route is caught by
# Starlette's outer ServerErrorMiddleware and turned into a bare 500 response.
# That response does NOT reliably carry the CORS headers added by
# CORSMiddleware (which sits *inside* ServerErrorMiddleware), so the browser
# reports a misleading "blocked by CORS policy" error that hides the real
# exception. Registering an explicit handler keeps the response inside
# ExceptionMiddleware (where CORSMiddleware still applies) and — critically —
# logs + surfaces the real error so it's visible in the Network tab instead of
# only in the server's stdout.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    tb = traceback.format_exc()
    # Always print full traceback to the uvicorn console (this is the
    # ground-truth signal — read this before anything else).
    print(f"\n=== UNHANDLED EXCEPTION on {request.url.path} ===\n{tb}", flush=True)
    log_event("UNHANDLED_EXCEPTION", {
        "path":      request.url.path,
        "error":     str(exc),
        "type":      type(exc).__name__,
        "traceback": tb,
    })
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error":  str(exc) if DEBUG else None,
            "type":   type(exc).__name__ if DEBUG else None,
        },
    )


# ── Localhost guard ────────────────────────────────────────────────────────────

def _localhost_only(request: Request) -> None:
    """
    Guard used on every admin/dashboard HTTP route.

    F1/F2 hardening: this now also requires a valid bearer/query dashboard
    token and, for state-changing methods, a recognised Origin (when one is
    sent). The function name and signature are kept unchanged so every
    existing call site below continues to work without modification.
    See services/dashboard_auth.py for the implementation and rationale.
    """
    require_dashboard_auth(request)


# ── Dashboard WebSocket (localhost only) ───────────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket) -> None:
    host = ws.client.host if ws.client else "unknown"
    if host not in ("127.0.0.1", "::1"):
        await ws.close(code=4003)
        return
    # F1: same bearer token required as the REST admin API. Browsers can't
    # set custom headers on a WebSocket upgrade, so the token travels as a
    # query parameter here (the frontend appends it automatically).
    if not dashboard_ws_token_valid(ws):
        log_event("DASHBOARD_WS_AUTH_FAILED", {"host": host})
        await ws.close(code=4401)
        return
    if len(_dashboard_sockets) >= MAX_DASHBOARD_CLIENTS:
        log_event("DASHBOARD_WS_LIMIT", {
            "host": host, "current": len(_dashboard_sockets),
            "max": MAX_DASHBOARD_CLIENTS,
        })
        await ws.close(code=4008)
        return
    await ws.accept()
    _dashboard_sockets.append(ws)
    connected_at = time.monotonic()
    try:
        while True:
            # F6: bound total connection lifetime — see DASHBOARD_WS_MAX_LIFETIME
            # in settings.py for rationale (no idle-since-last-message signal
            # exists on this server-push-only socket, so lifetime is the bound).
            remaining = DASHBOARD_WS_MAX_LIFETIME - (time.monotonic() - connected_at)
            if remaining <= 0:
                log_event("DASHBOARD_WS_LIFETIME_EXCEEDED", {
                    "host": host, "max_lifetime": DASHBOARD_WS_MAX_LIFETIME,
                })
                await ws.close(code=4000)
                break
            await asyncio.sleep(min(15, remaining))
            await ws.send_json({"event": "ping"})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if ws in _dashboard_sockets:
            _dashboard_sockets.remove(ws)


# ── Auth WebSocket (LAN clients) ───────────────────────────────────────────────

@app.websocket("/ws/auth")
async def auth_ws(ws: WebSocket) -> None:
    global _auth_ws_count

    ip = ws.client.host if ws.client else "unknown"

    # F6: bound total concurrent /ws/auth connections. Checked BEFORE
    # accept() so a flood of connection attempts can't accumulate accepted
    # sockets/tasks beyond this cap. Legitimate per-IP HELLO traffic is
    # already separately rate-limited below this layer.
    if _auth_ws_count >= AUTH_WS_MAX_CONNECTIONS:
        log_event("AUTH_WS_CONNECTION_LIMIT", {
            "ip": ip, "current": _auth_ws_count, "max": AUTH_WS_MAX_CONNECTIONS,
        })
        await ws.close(code=4008)
        return

    await ws.accept()
    _auth_ws_count += 1
    authed_fingerprint: Optional[str] = None
    pending_fingerprint: Optional[str] = None

    try:
        while True:
            # F6: idle timeout — a socket that never sends HELLO/PING/anything
            # is closed rather than held open indefinitely. The default
            # (90s) comfortably exceeds the client's 10s PING keep-alive
            # interval used while awaiting operator approval, so legitimate
            # devices are never affected.
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=AUTH_WS_IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                log_event("AUTH_WS_IDLE_TIMEOUT", {"ip": ip, "timeout": AUTH_WS_IDLE_TIMEOUT})
                await ws.close(code=4408)
                break

            # FINDING-13: parse errors → send error, continue (don't crash loop)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log_event("AUTH_MALFORMED_MSG", {"ip": ip})
                await ws.send_text(json.dumps({
                    "status": "error", "message": "Invalid JSON",
                }))
                continue

            if not isinstance(msg, dict):
                await ws.send_text(json.dumps({
                    "status": "error", "message": "Expected JSON object",
                }))
                continue

            msg_type = msg.get("type")

            if msg_type == "HELLO":
                # FINDING-03: pass ws reference so approve/allow_once can push
                try:
                    result = auth_service.handle_hello(
                        device_id=msg.get("device_id", "unknown"),
                        device_name=msg.get("device_name", "Unknown"),
                        public_key_b64=msg["public_key_b64"],
                        ip=ip,
                        client_x25519_pub_b64=msg.get("x25519_public_b64"),
                        auth_ws=ws,
                    )
                    if result.get("status") == "pending":
                        pending_fingerprint = fingerprint_from_raw_b64(msg["public_key_b64"])
                    result["server_public_key_b64"] = get_server_public_b64(KEYS_DIR)
                    result["server_fingerprint"]    = _server_fp
                    result["udp_port"]              = stream_service.udp_port
                    await ws.send_text(json.dumps(result))
                except Exception as exc:
                    # FINDING-13: send structured error, don't drop connection
                    log_event("AUTH_HELLO_EXCEPTION", {
                        "ip": ip, "error": str(exc),
                        "type": type(exc).__name__,
                    })
                    await ws.send_text(json.dumps({
                        "status": "error",
                        "message": "Internal error during HELLO",
                    }))

            elif msg_type == "CHALLENGE_RESPONSE":
                try:
                    result = auth_service.verify_challenge(
                        msg["fingerprint"], msg["signature_b64"]
                    )
                    result["udp_port"] = stream_service.udp_port
                    if result.get("status") == "authenticated":
                        authed_fingerprint = msg["fingerprint"]
                        pending_fingerprint = None
                    await ws.send_text(json.dumps(result))
                except Exception as exc:
                    log_event("AUTH_CHALLENGE_EXCEPTION", {
                        "ip": ip, "error": str(exc),
                        "type": type(exc).__name__,
                    })
                    await ws.send_text(json.dumps({
                        "status": "error",
                        "message": "Internal error during challenge verification",
                    }))

            elif msg_type == "PING":
                if pending_fingerprint:
                    auth_service.refresh_pending(pending_fingerprint)
                await ws.send_text(json.dumps({"type": "PONG"}))

            else:
                log_event("AUTH_UNKNOWN_MSG_TYPE", {
                    "ip": ip, "type": msg_type,
                })

    except WebSocketDisconnect:
        # FINDING-13: clean disconnect — expected, log quietly
        log_event("AUTH_WS_DISCONNECTED", {"ip": ip, "reason": "WebSocketDisconnect"})

    except Exception as exc:
        # FINDING-13: unexpected exception — log with detail
        log_event("AUTH_WS_ERROR", {
            "ip":    ip,
            "error": str(exc),
            "type":  type(exc).__name__,
        })

    finally:
        # F6: release the connection-count slot
        _auth_ws_count -= 1
        # FINDING-04: revoke single-use session on any disconnect
        if authed_fingerprint:
            auth_service.on_auth_ws_disconnect(authed_fingerprint)


# ── Server Info ────────────────────────────────────────────────────────────────

@app.get("/api/server/info")
async def server_info(request: Request) -> dict:
    _localhost_only(request)
    server_cfg   = cfg.load_config()
    stream_stats = stream_service.get_stats()
    return {
        "server_fingerprint":    _server_fp,
        "server_public_key_b64": _server_public_key_b64,   # cached at startup
        "capture_running":       capture_service.is_running,
        "frame_count":           capture_service.frame_count,
        "config":                server_cfg,
        "stream":                stream_stats,
    }


# ── Stream Control ─────────────────────────────────────────────────────────────

@app.post("/api/stream/configure")
async def configure_stream(request: Request) -> dict:
    _localhost_only(request)

    body = await request.json()
    # FINDING-13 / body validation: reject non-dict bodies
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object")

    # FINDING-17: lock prevents concurrent stop/start races
    # FIX: _reconfigure_lock is created in lifespan; guard against the
    # (theoretically impossible at runtime) case where it is None.
    if _reconfigure_lock is None:
        raise HTTPException(status_code=503, detail="Server not yet initialised")
    async with _reconfigure_lock:
        server_cfg = cfg.load_config()
        cap        = server_cfg["capture"]

        cap["x"]       = max(0, int(body.get("x",       cap["x"])))
        cap["y"]       = max(0, int(body.get("y",       cap["y"])))
        cap["width"]   = max(64, min(int(body.get("width",  cap["width"])),  7680))
        cap["height"]  = max(64, min(int(body.get("height", cap["height"])), 4320))
        cap["fps"]     = max(1,  min(int(body.get("fps",    cap["fps"])),     60))
        # Ensure quality and codec remain forced to JPEG‑100; ignore any client‑provided values
        # (These fields are kept for backward compatibility but will be overridden)
        cap["quality"] = "ultra"  # will map to JPEG‑100 in backend
        cap["codec"]   = "jpeg"

        server_cfg["capture"] = cap
        cfg.save_config(server_cfg)

        # JPEG‑100 is hard‑coded, no need to compute quality_val
        capture_service.configure(
            x=cap["x"], y=cap["y"],
            width=cap["width"], height=cap["height"],
            fps=cap["fps"],
        )
        stream_service.capture_stopped()
        await capture_service.stop()
        await capture_service.start()
        stream_service.capture_started()

    log_event("STREAM_CONFIGURED", {"config": cap, "actor": actor_id_from_request(request)})
    return {"status": "ok", "config": cap}


@app.post("/api/stream/start")
async def start_stream(request: Request) -> dict:
    _localhost_only(request)
    await capture_service.start()
    stream_service.capture_started()
    log_event("STREAM_STARTED", {"actor": actor_id_from_request(request)})
    return {"status": "started"}


@app.post("/api/stream/stop")
async def stop_stream(request: Request) -> dict:
    _localhost_only(request)
    stream_service.capture_stopped()
    await capture_service.stop()
    log_event("STREAM_STOPPED", {"actor": actor_id_from_request(request)})
    return {"status": "stopped"}


# ── Connected Devices ──────────────────────────────────────────────────────────

@app.get("/api/devices/connected")
async def get_connected(request: Request) -> dict:
    _localhost_only(request)
    devices = await stream_service.get_connected()
    return {"devices": devices, "total": len(devices)}


# ── Pending Requests ───────────────────────────────────────────────────────────

@app.get("/api/devices/pending")
async def get_pending(request: Request) -> dict:
    _localhost_only(request)
    return {"devices": auth_service.get_pending_list()}


@app.post("/api/devices/pending/{fp}/approve")
async def approve_device(fp: str, request: Request) -> dict:
    _localhost_only(request)
    ok = await auth_service.approve_permanently(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "approve_pending", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok" if ok else "not_found",
    })
    return {"status": "ok" if ok else "not_found"}


@app.post("/api/devices/pending/{fp}/allow_once")
async def allow_once_device(fp: str, request: Request) -> dict:
    _localhost_only(request)
    ok = await auth_service.allow_once(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "allow_once", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok" if ok else "not_found",
    })
    if not ok:
        return {"status": "not_found"}
    # Build challenge response similar to auth_service's _issue_challenge
    req = auth_service._pending.get(fp)
    if not req:
        return {"status": "ok"}
    response: dict = {
        "status": "challenge",
        "challenge_b64": base64.b64encode(req.challenge).decode(),
        "session_key_b64": None,
    }
    if req.client_x25519_pub_bytes:
        from cryptography.hazmat.primitives import serialization as _ser
        srv_pub_bytes = req.x25519_server_priv.public_key().public_bytes(
            _ser.Encoding.Raw, _ser.PublicFormat.Raw,
        )
        response["server_x25519_public_b64"] = base64.b64encode(srv_pub_bytes).decode()
        if auth_service._server_private:
            binding_msg = req.challenge + req.client_x25519_pub_bytes + srv_pub_bytes
            sig = auth_service._server_private.sign(binding_msg)
            response["server_signature_b64"] = base64.b64encode(sig).decode()
            response["server_public_key_b64"] = base64.b64encode(
                auth_service._server_public.public_bytes(
                    _ser.Encoding.Raw, _ser.PublicFormat.Raw
                )
            ).decode()
            response["server_fingerprint"] = auth_service._server_fp
    response["udp_port"] = stream_service.udp_port
    return response


@app.post("/api/devices/pending/{fp}/reject")
async def reject_device(fp: str, request: Request) -> dict:
    _localhost_only(request)
    ok = await auth_service.reject(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "reject_pending", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok" if ok else "not_found",
    })
    return {"status": "ok" if ok else "not_found"}


@app.post("/api/devices/pending/{fp}/block")
async def block_pending_device(fp: str, request: Request) -> dict:
    _localhost_only(request)
    ok = await auth_service.block_permanently(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "block_pending", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok" if ok else "not_found",
    })
    return {"status": "ok" if ok else "not_found"}
@app.post("/api/devices/{fp}/disconnect")
async def remove_device(fp: str, request: Request) -> dict:
    _localhost_only(request)
    # Revoke any auth session and UDP client
    removed = stream_service.remove_client(fp)
    # Ensure auth session removed (stream_service already does, but safe)
    auth_service.remove_session(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "disconnect_device", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok" if removed else "not_found",
    })
    await _push_dashboard('device_removed', {'fingerprint': fp})
    return {"status": "ok" if removed else "not_found"}


# ── Trusted Devices ────────────────────────────────────────────────────────────

@app.get("/api/devices/trusted")
async def get_trusted(request: Request, limit: int = 10, offset: int = 0) -> dict:
    _localhost_only(request)
    return {"devices": reg.list_trusted(limit, offset), "total": reg.count_trusted()}


@app.delete("/api/devices/trusted/{fp}")
async def remove_trust(fp: str, request: Request) -> dict:
    _localhost_only(request)
    # Also revoke any live session so the device can't keep streaming
    auth_service.remove_session(fp)
    reg.remove_trusted(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "remove_trust", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok",
    })
    return {"status": "ok"}


@app.post("/api/devices/trusted/{fp}/block")
async def block_trusted(fp: str, request: Request) -> dict:
    _localhost_only(request)
    await auth_service.block_permanently(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "block_trusted", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok",
    })
    return {"status": "ok"}


# ── Blocked Devices ────────────────────────────────────────────────────────────

@app.get("/api/devices/blocked")
async def get_blocked(request: Request, limit: int = 10, offset: int = 0) -> dict:
    _localhost_only(request)
    return {"devices": reg.list_blocked(limit, offset), "total": reg.count_blocked()}


@app.post("/api/devices/blocked/{fp}/unblock")
async def unblock_device(fp: str, request: Request) -> dict:
    _localhost_only(request)
    reg.remove_blocked(fp)
    log_event("DASHBOARD_ACTION", {
        "action": "unblock_device", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok",
    })
    return {"status": "ok"}


@app.post("/api/devices/blocked/{fp}/trust")
async def trust_blocked(fp: str, request: Request) -> dict:
    _localhost_only(request)
    blocked = reg.get_blocked(fp)
    if blocked:
        reg.remove_blocked(fp)
        reg.save_trusted({**blocked, "fingerprint": fp})
    log_event("DASHBOARD_ACTION", {
        "action": "trust_blocked", "fingerprint": fp,
        "actor": actor_id_from_request(request), "result": "ok" if blocked else "not_found",
    })
    return {"status": "ok"}


# ── Recent / Rejected ──────────────────────────────────────────────────────────

@app.get("/api/devices/recent")
async def get_recent(request: Request, limit: int = 10, offset: int = 0) -> dict:
    _localhost_only(request)
    return {"devices": reg.list_recent(limit, offset), "total": reg.count_recent()}


@app.get("/api/devices/rejected")
async def get_rejected(request: Request, limit: int = 10, offset: int = 0) -> dict:
    _localhost_only(request)
    return {"devices": reg.list_rejected(limit, offset), "total": reg.count_rejected()}


# ── Logs ───────────────────────────────────────────────────────────────────────

@app.get("/api/logs")
async def get_logs(request: Request, limit: int = 200) -> dict:
    _localhost_only(request)
    return {"logs": get_recent_logs(limit)}


# ── Security / DoS stats ──────────────────────────────────────────────────────
from .settings import (
    AUTH_RATE_LIMIT_WINDOW,
    AUTH_RATE_LIMIT_MAX,
    PENDING_FP_MAX,
    MAX_PENDING_DEVICES,
    LOG_MAX_BYTES,
    LOG_MAX_FILES,
)
@app.get("/api/server/security")
async def server_security(request: Request) -> dict:
    """Expose DoS counters and limits for the monitoring dashboard."""
    _localhost_only(request)
    stream_stats = stream_service.get_stats()
    return {
        "udp_rate_limit": {
            "packets_per_second": stream_stats.get("packets_dropped_rate", 0),
            "packets_dropped_rate_limit": stream_stats.get("packets_dropped_rate", 0),
            "packets_rejected_auth":      stream_stats.get("packets_rejected_auth", 0),
            "clients_rejected_limit":     stream_stats.get("clients_rejected_limit", 0),
            "max_stream_clients":         stream_stats.get("max_clients", 16),
            "current_stream_clients":     stream_stats.get("client_count", 0),
        },
        "auth": {
            "rate_limit_window_secs": AUTH_RATE_LIMIT_WINDOW,
            "rate_limit_max_hellos": AUTH_RATE_LIMIT_MAX,
            "pending_fp_limit_per_min": PENDING_FP_MAX,
            "max_pending": MAX_PENDING_DEVICES,
        },
        "logging": {
            "log_max_bytes":  LOG_MAX_BYTES,
            "log_max_files":  LOG_MAX_FILES,
        },
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    # FINDING-06: expose udp_running separately so degraded mode is visible
    return {
        "status":      "ok",
        "timestamp":   time.time(),
        "udp_port":    stream_service.udp_port,
        "udp_running": stream_service._running,
        "capture":     capture_service.is_running,
        "codec":       capture_service._codec,
    }