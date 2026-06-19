from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent / ".env")

DEBUG = os.getenv("DEBUG", "true").lower() == "true"

SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8766"))

UDP_HOST = os.getenv("UDP_HOST", "0.0.0.0")
UDP_PORT = int(os.getenv("UDP_PORT", "8765"))

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