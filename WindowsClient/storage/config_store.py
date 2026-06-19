import json
import logging
from pathlib import Path
from config.settings import CACHE_DIR

logger = logging.getLogger("ConfigStore")
CONFIG_FILE = CACHE_DIR / "client_config.json"

def load_client_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Failed to read client config: %s", exc)
    return {}

def save_client_config(config: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as exc:
        logger.error("Failed to save client config: %s", exc)
