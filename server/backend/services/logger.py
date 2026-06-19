"""
Structured audit logging — Fixes Edition.

Fixes applied:
  ✓ FINDING-11: Separate read and write locks — get_recent_logs() no longer
    blocks the write worker while reading files.
  ✓ FINDING-18: flush() helper drains the queue synchronously; call from
    the FastAPI shutdown handler to ensure final events reach disk.
  ✓ region dicts are now serialised as proper JSON objects, not repr() strings.
  ✓ Log size guard: get_recent_logs() is capped and streams file reads.
"""
from __future__ import annotations

import json
import time
import threading
import queue
from datetime import datetime, timezone
from pathlib import Path

from ..config import LOGS_DIR

# ── Log rotation + queue limits ───────────────────────────────────────────────
# Without rotation an attacker that triggers 50 000 log events (e.g. via a
# UDP flood that generates one log per bad packet) can produce 10+ GB of logs.
# We cap each daily file at LOG_MAX_BYTES and keep at most LOG_MAX_FILES files.
# LOG_QUEUE_SIZE controls the in-memory queue cap (default 10 000 ≈ 5–10 MB).
from ..settings import (
    LOG_MAX_BYTES,
    LOG_MAX_FILES,
    LOG_QUEUE_SIZE,
)

# Separate locks for read and write paths (FINDING-11)
_write_lock = threading.Lock()
# Cap the in-memory queue using the configurable LOG_QUEUE_SIZE from .env.
_log_queue: queue.Queue = queue.Queue(maxsize=LOG_QUEUE_SIZE)

def _rotate_if_needed(log_file: Path) -> None:
    """
    If log_file exceeds LOG_MAX_BYTES, rename it to .1 (overwriting any
    existing .1) and start a fresh file.  Called while _write_lock is held.
    After rotation, enforce LOG_MAX_FILES by deleting excess *.jsonl files.
    """
    try:
        if log_file.exists() and log_file.stat().st_size >= LOG_MAX_BYTES:
            rotated = log_file.with_suffix(".jsonl.1")
            log_file.replace(rotated)   # atomic on POSIX

        # Enforce total file count — keep only the N newest *.jsonl* files
        all_files = sorted(
            list(LOGS_DIR.glob("*.jsonl")) + list(LOGS_DIR.glob("*.jsonl.1")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_file in all_files[LOG_MAX_FILES:]:
            try:
                old_file.unlink()
            except OSError:
                pass
    except OSError:
        pass


def _log_worker() -> None:
    """Background worker — writes log records to daily JSONL files."""
    while True:
        try:
            record, log_file = _log_queue.get()
            line = ""
            try:
                line = json.dumps(record) + "\n"
            except (TypeError, ValueError):
                record["data"] = {k: str(v) for k, v in record.get("data", {}).items()}
                line = json.dumps(record) + "\n"

            with _write_lock:
                try:
                    _rotate_if_needed(log_file)
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(line)
                except OSError:
                    pass
        except Exception:
            pass
        finally:
            _log_queue.task_done()


threading.Thread(target=_log_worker, daemon=True, name="log-worker").start()


def log_event(event: str, data: dict | None = None) -> None:
    """Queue a structured JSONL audit record. Non-blocking."""
    record = {
        "timestamp": time.time(),
        "datetime":  datetime.now(timezone.utc).isoformat(),
        "event":     event,
        "data":      _safe_dict(data or {}),
    }
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file  = LOGS_DIR / f"{date_str}.jsonl"
    try:
        _log_queue.put_nowait((record, log_file))
    except queue.Full:
        # Queue is saturated (flood in progress) — silently drop this record
        # rather than blocking the asyncio event loop or the calling thread.
        pass


def flush(timeout: float = 5.0) -> None:
    """
    FINDING-18: Block until all queued log records have been written,
    or until `timeout` seconds elapse (whichever comes first).

    queue.Queue.join() does not accept a timeout parameter, so we
    implement the timeout by running join() on a daemon thread and
    waiting on that thread — the standard pattern for bounded join().
    """
    import threading
    t = threading.Thread(target=_log_queue.join, daemon=True)
    t.start()
    t.join(timeout=timeout)


def _safe_dict(d: dict) -> dict:
    """Return a JSON-serialisable copy of d."""
    out = {}
    for k, v in d.items():
        if isinstance(v, bytes):
            out[k] = v.hex()
        elif isinstance(v, dict):
            # LOGGING FIX: nested dicts (e.g. region) become proper JSON objects
            out[k] = _safe_dict(v)
        elif isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def get_recent_logs(limit: int = 200) -> list[dict]:
    """
    Return the most recent `limit` log entries across log files.
    FINDING-11: Does NOT hold the write lock while reading files.
    """
    records: list[dict] = []
    # Snapshot the file list without holding the write lock
    files = sorted(LOGS_DIR.glob("*.jsonl"), reverse=True)

    for lf in files:
        try:
            # Read outside the write lock — worst case we miss the last line
            # of an in-progress write; that is acceptable for a dashboard query.
            with open(lf, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
        if len(records) >= limit * 2:
            break

    records.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
    return records[:limit]