import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
# Default matches the server's AUTH_BIND_PORT default (backend/.env /
# backend/settings.py) — the auth/streaming listener, separate from the
# server's dashboard port (8766). See WindowsClient/.env for details.
AUTH_PORT = int(os.getenv("AUTH_PORT", "8767"))
UDP_PORT = int(os.getenv("UDP_PORT", "8765"))

DEVICE_ID = os.getenv("DEVICE_ID", "vm-client")
DEVICE_NAME = os.getenv("DEVICE_NAME", "VirtualMachine")

# Storage paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

KEYS_DIR = DATA_DIR / "keys"
CACHE_DIR = DATA_DIR / "cache"
SESSIONS_DIR = DATA_DIR / "sessions"
TRUSTED_SERVERS_DIR = DATA_DIR / "trusted_servers"
LOGS_DIR = BASE_DIR / "logs"

for d in [KEYS_DIR, CACHE_DIR, SESSIONS_DIR, TRUSTED_SERVERS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)