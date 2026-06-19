"""
Configuration management — Fixes Edition.

Fixes applied:
  ✓ FINDING-10: save_config() uses atomic write (write .tmp → os.replace).
  ✓ Directory creation moved to initialize() so it doesn't run on test import.
    startup() in main.py calls initialize() explicitly.
  ✓ backend/data/config/ added to .gitignore recommendation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

TRUSTED_DIR  = DATA_DIR / "trusted_clients"
BLOCKED_DIR  = DATA_DIR / "blocked_clients"
RECENT_DIR   = DATA_DIR / "recent_clients"
REJECTED_DIR = DATA_DIR / "rejected_clients"
LOGS_DIR     = DATA_DIR / "logs"
CONFIG_DIR   = DATA_DIR / "config"
KEYS_DIR     = DATA_DIR / "keys"

_CONFIG_FILE = CONFIG_DIR / "server_config.json"

_DEFAULTS: dict = {
    "capture": {
        "x": 0, "y": 0,
        "width": 1280, "height": 720,
        "fps": 20,
        "quality": "medium",
        "codec": "h264",
    },
    "server": {
        "host":           "0.0.0.0",
        "port":           8765,
        "dashboard_host": "127.0.0.1",
        "dashboard_port": 5173,
    },
    "stream": {
        "preset": "custom",
        "jpeg_quality_map": {
            "low": 30, "medium": 60, "high": 80, "ultra": 95,
        },
    },
}


def initialize() -> None:
    """Create all required data directories. Called explicitly from startup()."""
    for d in [TRUSTED_DIR, BLOCKED_DIR, RECENT_DIR, REJECTED_DIR,
              LOGS_DIR, CONFIG_DIR, KEYS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                saved = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupted config — fall back to defaults
            return _deep_copy(_DEFAULTS)
        merged = _deep_copy(_DEFAULTS)
        for section, vals in saved.items():
            if section in merged and isinstance(vals, dict):
                merged[section].update(vals)
            else:
                merged[section] = vals
        return merged
    return _deep_copy(_DEFAULTS)


def save_config(cfg: dict) -> None:
    """FINDING-10: Atomic write."""
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, _CONFIG_FILE)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def get_jpeg_quality(cfg: dict) -> int:
    quality_name = cfg["capture"].get("quality", "medium")
    return cfg["stream"]["jpeg_quality_map"].get(quality_name, 60)


def _deep_copy(d: dict) -> dict:
    """Simple deep copy for nested dicts (no external deps)."""
    result = {}
    for k, v in d.items():
        result[k] = _deep_copy(v) if isinstance(v, dict) else v
    return result