from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent / ".env")

DEBUG = os.getenv("DEBUG", "true").lower() == "true"

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8766"))

UDP_HOST = os.getenv("UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("UDP_PORT", "8765"))

# ── LAN streaming: dual-listener split ──────────────────────────────────────
# SERVER_HOST/SERVER_PORT (above) is the dashboard/admin listener and MUST
# stay loopback — enforced separately in run.py regardless of this value.
#
# AUTH_BIND_HOST/AUTH_BIND_PORT is a SECOND uvicorn listener serving only
# /ws/auth (+ /health) — see LANSurfaceFilter in main.py and run.py. This
# is what makes the Windows client's ws://{SERVER_IP}:{AUTH_PORT}/ws/auth
# reachable from another machine on the LAN without exposing the dashboard
# or any admin API.
#
# IMPORTANT: this MUST be a different port number than SERVER_PORT. A
# socket bound to 0.0.0.0:N and one bound to 127.0.0.1:N cannot coexist —
# 0.0.0.0 is a wildcard that already covers 127.0.0.1 at that port, so the
# second bind fails with "Address already in use". Defaults to
# SERVER_PORT + 1 (8767 given the project's default 8766) for that reason.
#
# Set WindowsClient/.env's AUTH_PORT to match this value when the client
# is on a different machine than the server (see migration notes).
AUTH_BIND_HOST = os.getenv("AUTH_BIND_HOST", "0.0.0.0")
AUTH_BIND_PORT = int(os.getenv("AUTH_BIND_PORT", str(SERVER_PORT + 1)))

CORS_ORIGINS = [
    x.strip()
    for x in os.getenv("CORS_ORIGINS", "").split(",")
    if x.strip()
]

MAX_DASHBOARD_CLIENTS = int(
    os.getenv("MAX_DASHBOARD_CLIENTS", "10")
)

CHALLENGE_TTL = int(
    os.getenv("CHALLENGE_TTL", "60")
)

SESSION_TTL = int(
    os.getenv("SESSION_TTL", "1800")
)

MAX_PENDING_DEVICES = int(
    os.getenv("MAX_PENDING_DEVICES", "100")
)

AUTH_RATE_LIMIT_WINDOW = int(
    os.getenv("AUTH_RATE_LIMIT_WINDOW", "60")
)

AUTH_RATE_LIMIT_MAX = int(
    os.getenv("AUTH_RATE_LIMIT_MAX", "10")
)

PENDING_FP_WINDOW = int(
    os.getenv("PENDING_FP_WINDOW", "60")
)

PENDING_FP_MAX = int(
    os.getenv("PENDING_FP_MAX", "5")
)

SESSION_GC_INTERVAL = int(
    os.getenv("SESSION_GC_INTERVAL", "60")
)

CLIENT_TIMEOUT = int(
    os.getenv("CLIENT_TIMEOUT", "30")
)

HEARTBEAT_TIMESTAMP_SKEW = int(
    os.getenv("HEARTBEAT_TIMESTAMP_SKEW", "30")
)

NONCE_HISTORY_LEN = int(
    os.getenv("NONCE_HISTORY_LEN", "64")
)

UDP_RATE_LIMIT_PACKETS = int(
    os.getenv("UDP_RATE_LIMIT_PACKETS", "200")
)

UDP_RATE_LIMIT_WINDOW = float(
    os.getenv("UDP_RATE_LIMIT_WINDOW", "1")
)

MAX_STREAM_CLIENTS = int(
    os.getenv("MAX_STREAM_CLIENTS", "16")
)

MAX_CAPTURE_ERRORS = int(
    os.getenv("MAX_CAPTURE_ERRORS", "10")
)

ERROR_BACKOFF_SECS = float(
    os.getenv("ERROR_BACKOFF_SECS", "5")
)

KEYFRAME_INTERVAL_SECS = float(
    os.getenv("KEYFRAME_INTERVAL_SECS", "2")
)

LOG_MAX_BYTES = int(
    os.getenv("LOG_MAX_BYTES", "10485760")
)

LOG_MAX_FILES = int(
    os.getenv("LOG_MAX_FILES", "5")
)

LOG_QUEUE_SIZE = int(
    os.getenv("LOG_QUEUE_SIZE", "10000")
)

# ── F6: /ws/auth connection-level resource limits ────────────────────────
# Unlike HELLO messages (already rate-limited via AUTH_RATE_LIMIT_*), the
# WebSocket *connection itself* previously had no cap and no idle timeout —
# a client could open many sockets and never send anything, holding an
# asyncio task + TCP socket indefinitely. These two settings bound that.
AUTH_WS_MAX_CONNECTIONS = int(
    os.getenv("AUTH_WS_MAX_CONNECTIONS", "100")
)

# Must comfortably exceed the client's PING keep-alive interval (10s,
# see WindowsClient/services/auth_service.py) so legitimate pending
# devices are never disconnected while waiting for operator approval.
AUTH_WS_IDLE_TIMEOUT = float(
    os.getenv("AUTH_WS_IDLE_TIMEOUT", "90")
)

# ── F6: /ws/dashboard connection-lifetime bound ───────────────────────────
# The dashboard socket is server-push-only (client never sends anything
# after connecting), so an idle-timeout-since-last-message check doesn't
# apply the way it does for /ws/auth. Instead, cap the *total* lifetime of
# a single connection so a peer that never cleanly closes (e.g. a stalled
# browser tab, a network path that swallows the FIN) doesn't hold a slot
# under MAX_DASHBOARD_CLIENTS indefinitely. The frontend already
# auto-reconnects on close, so periodic forced reconnects are invisible
# to the operator.
DASHBOARD_WS_MAX_LIFETIME = float(
    os.getenv("DASHBOARD_WS_MAX_LIFETIME", "3600")
)