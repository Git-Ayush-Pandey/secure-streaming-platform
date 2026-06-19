"""
Device Registry Service — Fixes Edition.

Fixes applied:
  ✓ FINDING-10: All JSON writes use atomic write pattern (write to .tmp,
    then os.replace) — safe against crash mid-write on both POSIX and Windows.
  ✓ FINDING-10: startup_validate() scans all directories and logs/quarantines
    corrupted files so they do not silently block trusted devices.
  ✓ remove_trusted() now logs the removal (audit gap fix).
  ✓ remove_blocked() now logs the unblock action (audit gap fix).
  ✓ save_config() in config.py uses the same atomic pattern (see config.py).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, Literal

from ..config import (
    TRUSTED_DIR, BLOCKED_DIR, RECENT_DIR, REJECTED_DIR
)
from .logger import log_event

DeviceStatus = Literal["trusted", "blocked", "pending", "allow_once", "connected"]


def _fp_to_filename(fingerprint: str) -> str:
    return fingerprint.replace(":", "-") + ".json"


def _read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log_event("REGISTRY_READ_ERROR", {
            "path": str(path), "error": str(exc),
        })
        return None


def _write(path: Path, data: dict) -> None:
    """
    FINDING-10: Atomic write — write to .tmp then os.replace().
    os.replace() is atomic on POSIX; best-effort on Windows.
    """
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as exc:
        # Clean up tmp if replace failed
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        log_event("REGISTRY_WRITE_ERROR", {
            "path": str(path), "error": str(exc),
        })
        raise


def _delete(path: Path) -> None:
    if path.exists():
        path.unlink()


# ── Startup validation ─────────────────────────────────────────────────────────

def startup_validate() -> None:
    """
    FINDING-10: Scan all registry directories at startup.
    Corrupted JSON files are renamed to .corrupt for manual recovery.
    """
    for directory in (TRUSTED_DIR, BLOCKED_DIR, RECENT_DIR, REJECTED_DIR):
        for p in directory.glob("*.json"):
            try:
                with open(p) as f:
                    json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                corrupt_path = p.with_suffix(".corrupt")
                try:
                    p.rename(corrupt_path)
                except Exception:
                    pass
                log_event("REGISTRY_CORRUPTED_FILE", {
                    "path":    str(p),
                    "renamed": str(corrupt_path),
                    "error":   str(exc),
                })


# ── Trusted ────────────────────────────────────────────────────────────────────

def get_trusted(fingerprint: str) -> Optional[dict]:
    return _read(TRUSTED_DIR / _fp_to_filename(fingerprint))


def save_trusted(device: dict) -> None:
    fp = device["fingerprint"]
    existing = get_trusted(fp)
    if existing:
        existing.update({
            "device_id":      device.get("device_id",      existing.get("device_id")),
            "device_name":    device.get("device_name",    existing.get("device_name")),
            "public_key_b64": device.get("public_key_b64", existing.get("public_key_b64")),
            "last_seen":      device.get("last_seen",      time.time()),
            "last_ip":        device.get("last_ip",        existing.get("last_ip")),
            "accept_count":   existing.get("accept_count", 0) + device.get("_inc_accept", 0),
        })
        _write(TRUSTED_DIR / _fp_to_filename(fp), existing)
    else:
        record = {
            "device_id":        device["device_id"],
            "device_name":      device.get("device_name", "Unknown"),
            "fingerprint":      fp,
            "public_key_b64":   device["public_key_b64"],
            "first_approval":   time.time(),
            "last_seen":        time.time(),
            "last_ip":          device.get("last_ip", ""),
            "connection_count": 0,
            "accept_count":     1,
            "reject_count":     0,
            "block_count":      0,
        }
        _write(TRUSTED_DIR / _fp_to_filename(fp), record)


def remove_trusted(fingerprint: str) -> None:
    _delete(TRUSTED_DIR / _fp_to_filename(fingerprint))
    log_event("TRUSTED_REMOVED", {"fingerprint": fingerprint})   # audit gap fix


def list_trusted(limit: int = 10, offset: int = 0) -> list[dict]:
    items = []
    for p in sorted(TRUSTED_DIR.glob("*.json"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        d = _read(p)
        if d:
            items.append(d)
    return items[offset:offset + limit]


def count_trusted() -> int:
    return len(list(TRUSTED_DIR.glob("*.json")))


# ── Blocked ────────────────────────────────────────────────────────────────────

def get_blocked(fingerprint: str) -> Optional[dict]:
    return _read(BLOCKED_DIR / _fp_to_filename(fingerprint))


def save_blocked(device: dict) -> None:
    fp = device["fingerprint"]
    record = {
        "device_id":      device.get("device_id", ""),
        "device_name":    device.get("device_name", "Unknown"),
        "fingerprint":    fp,
        "public_key_b64": device.get("public_key_b64", ""),
        "block_time":     time.time(),
        "last_ip":        device.get("last_ip", ""),
        "block_count":    device.get("block_count", 1),
    }
    _write(BLOCKED_DIR / _fp_to_filename(fp), record)
    remove_trusted(fp)


def remove_blocked(fingerprint: str) -> None:
    _delete(BLOCKED_DIR / _fp_to_filename(fingerprint))
    log_event("DEVICE_UNBLOCKED", {"fingerprint": fingerprint})  # audit gap fix


def list_blocked(limit: int = 10, offset: int = 0) -> list[dict]:
    items = []
    for p in sorted(BLOCKED_DIR.glob("*.json"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        d = _read(p)
        if d:
            items.append(d)
    return items[offset:offset + limit]


def count_blocked() -> int:
    return len(list(BLOCKED_DIR.glob("*.json")))


# ── Recent Connections ─────────────────────────────────────────────────────────

def save_recent(device_id: str, fingerprint: str, ip: str,
                result: str, device_name: str = "Unknown") -> None:
    ts  = time.time()
    key = f"{fingerprint}-{int(ts)}"
    record = {
        "device_id":   device_id,
        "device_name": device_name,
        "fingerprint": fingerprint,
        "ip":          ip,
        "timestamp":   ts,
        "result":      result,
    }
    _write(RECENT_DIR / (_fp_to_filename(key)), record)
    _prune_dir(RECENT_DIR, max_keep=200)


def list_recent(limit: int = 10, offset: int = 0) -> list[dict]:
    items = []
    for p in sorted(RECENT_DIR.glob("*.json"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        d = _read(p)
        if d:
            items.append(d)
    return items[offset:offset + limit]


def count_recent() -> int:
    return len(list(RECENT_DIR.glob("*.json")))


# ── Rejected ───────────────────────────────────────────────────────────────────

def save_rejected(device_id: str, fingerprint: str, ip: str,
                  reason: str, device_name: str = "Unknown") -> None:
    ts  = time.time()
    key = f"{fingerprint}-{int(ts)}"
    record = {
        "device_id":   device_id,
        "device_name": device_name,
        "fingerprint": fingerprint,
        "ip":          ip,
        "timestamp":   ts,
        "reason":      reason,
    }
    _write(REJECTED_DIR / (_fp_to_filename(key)), record)
    _prune_dir(REJECTED_DIR, max_keep=200)


def list_rejected(limit: int = 10, offset: int = 0) -> list[dict]:
    items = []
    for p in sorted(REJECTED_DIR.glob("*.json"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        d = _read(p)
        if d:
            items.append(d)
    return items[offset:offset + limit]


def count_rejected() -> int:
    return len(list(REJECTED_DIR.glob("*.json")))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _prune_dir(directory: Path, max_keep: int) -> None:
    files = sorted(directory.glob("*.json"), key=lambda f: f.stat().st_mtime)
    while len(files) > max_keep:
        files.pop(0).unlink()


def get_device_status(fingerprint: str) -> DeviceStatus:
    if get_trusted(fingerprint):
        return "trusted"
    if get_blocked(fingerprint):
        return "blocked"
    return "pending"


def update_trusted_stats(fingerprint: str, ip: str) -> None:
    path = TRUSTED_DIR / _fp_to_filename(fingerprint)
    d    = _read(path)
    if d:
        d["last_seen"]        = time.time()
        d["last_ip"]          = ip
        d["connection_count"] = d.get("connection_count", 0) + 1
        _write(path, d)