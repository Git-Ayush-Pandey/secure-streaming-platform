import json
import logging
from config.settings import SESSIONS_DIR

logger = logging.getLogger("LocalDB")
SESSION_CACHE_FILE = SESSIONS_DIR / "session_cache.json"

def get_cached_session() -> dict | None:
    """Load cached session information."""
    if SESSION_CACHE_FILE.exists():
        try:
            with open(SESSION_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read session cache: {e}")
    return None

def save_session_cache(session_data: dict) -> None:
    """Cache current session information."""
    try:
        with open(SESSION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write session cache: {e}")

def clear_session_cache() -> None:
    """Invalidate and remove session cache."""
    try:
        if SESSION_CACHE_FILE.exists():
            SESSION_CACHE_FILE.unlink()
    except Exception as e:
        logger.error(f"Failed to clear session cache: {e}")
