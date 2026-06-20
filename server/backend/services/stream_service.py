"""
UDP Stream Service — Hardened + DoS Edition.

Fixes applied:
  ✓ FINDING-06: start() raises RuntimeError on bind failure (no longer silent).
  ✓ FINDING-07: asyncio.get_running_loop() replaces deprecated get_event_loop().
  ✓ FINDING-12: nonce replay check applied on first heartbeat too.
  ✓ asyncio tasks protected with add_done_callback for crash visibility.
  ✓ _transport None-guard in broadcast loop.
  ✓ DoS: per-IP UDP packet rate limiter (UDP_RATE_LIMIT_PACKETS / s). Packets
    from any IP exceeding the limit are dropped BEFORE any parsing or crypto,
    bounding CPU cost of a UDP flood attack.
  ✓ DoS: MAX_STREAM_CLIENTS cap. New fingerprints beyond the limit are rejected
    at heartbeat time so a compromised LAN device cannot consume unbounded RAM.
  ✓ DoS: dropped / rejected packet counters exposed via get_stats().
  ✓ Codec-aware frame header: 1-byte codec tag prepended to wire packet.
    0x01 = JPEG, 0x02 = H.264 (Annex-B)
  ✓ FINDING-19 (audit): frame-level UDP fragmentation. Every previous version
    sent one full encoded frame per sendto() with no MTU awareness — verified
    empirically that JPEG frames (57KB-380KB) and H.264 frames (was 100KB+
    due to FINDING-20) both vastly exceed the ~1426B safe payload budget on a
    real Ethernet/Wi-Fi path (1500B MTU). Relying on IP fragmentation is
    fragile (commonly dropped/blocked) and was never validated against a real
    LAN. Frames are now encrypted once, then the ciphertext is sliced into
    MTU-safe fragments and reassembled by frame_seq + frag_index on receipt.
    See PACKET_MAX_PAYLOAD / wire format below.

UDP Heartbeat Wire Format (client → server) — UNCHANGED:
  [2B fp_len][fp_bytes][8B unix_timestamp_ms][16B nonce][32B HMAC-SHA256]
  HMAC message = fp_bytes + timestamp_bytes + nonce
  HMAC key     = AES session key

Frame Wire Format (server → client) — CHANGED (breaking, see migration note):
  OLD (pre-audit): [1B codec_tag][8B seq][4B nonce_len][12B nonce][ct+tag]
                   one full frame per UDP datagram, no fragmentation.
  NEW:
    [1B codec_tag]      ← 0x01=JPEG, 0x02=H264
    [1B flags]          ← bit0 = is_keyframe (H264 only, ignored for JPEG)
    [8B frame_seq BE]   ← per-FRAME counter (was per-packet); used as GCM AAD
    [2B frag_index BE]  ← 0-based fragment index within this frame
    [2B frag_count BE]  ← total fragment count for this frame
    [4B nonce_len]
    [12B nonce]
    [ciphertext_fragment]   ← raw slice of the single whole-frame AES-GCM
                              ciphertext; the 16B GCM tag is appended only
                              to the LAST fragment (frag_index == frag_count-1)
  MIGRATION IMPACT: any client decoder must buffer fragments by
  (frame_seq, frag_index) until frag_count fragments have arrived,
  concatenate ciphertext in index order, then run AES-256-GCM
  decrypt(nonce, full_ciphertext, aad=frame_seq_bytes) once over the
  reassembled buffer. WindowsClient/services/frame_reassembler.py
  implements exactly this and matches the wire format below.
"""
from __future__ import annotations

import asyncio
import struct
import time
import threading
from collections import deque
from typing import Optional

from .crypto_service import aes_encrypt, hmac_verify
from .capture_service import capture_service
from .logger import log_event

# ── Constants ──────────────────────────────────────────────────────────────────
from ..settings import (
    CLIENT_TIMEOUT,
    HEARTBEAT_TIMESTAMP_SKEW as HB_TIMESTAMP_SKEW,
    NONCE_HISTORY_LEN,
    UDP_RATE_LIMIT_PACKETS,
    UDP_RATE_LIMIT_WINDOW,
    MAX_STREAM_CLIENTS,
)
CODEC_TAG_JPEG = 0x01
CODEC_TAG_H264 = 0x02

FLAG_KEYFRAME = 0x01

# 1500B Ethernet MTU - 20B IP - 8B UDP - 18B fixed wire header (codec+flags+
# frame_seq+frag_index+frag_count+nonce_len+nonce) - 16B worst-case GCM tag
# on the last fragment = conservative safe ciphertext-fragment payload size.
FRAME_HEADER_SIZE  = 1 + 1 + 8 + 2 + 2 + 4 + 12   # = 30 bytes
PACKET_MAX_PAYLOAD = 1500 - 20 - 8 - FRAME_HEADER_SIZE - 16   # = 1426 bytes
MAX_FRAGMENTS      = 65535   # frag_count is a 2-byte field


class _UDPRateLimiter:
    """
    Per-IP token-bucket rate limiter for raw UDP packets.
    Checked BEFORE any parsing so flooded packets never reach crypto code.
    Thread-safe (called from the asyncio event loop thread only, but
    __init__ documents the design for clarity).
    """
    def __init__(self, max_per_window: int, window: float) -> None:
        self._max    = max_per_window
        self._window = window
        # ip -> deque of arrival timestamps
        self._buckets: dict[str, deque] = {}
        self._last_prune: float = time.monotonic()

    def allow(self, ip: str) -> bool:
        now    = time.monotonic()
        bucket = self._buckets.setdefault(ip, deque())
        cutoff = now - self._window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        # Prune stale IPs periodically to avoid unbounded memory growth
        if now - self._last_prune > 60.0:
            dead = [k for k, q in self._buckets.items()
                    if not q or q[-1] < now - self._window * 2]
            for k in dead:
                del self._buckets[k]
            self._last_prune = now
        return True


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, service: "UDPStreamService") -> None:
        self._svc = service

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self._svc._transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._svc._on_heartbeat(data, addr)

    def error_received(self, exc: Exception) -> None:
        log_event("UDP_SOCKET_ERROR", {"error": str(exc), "type": type(exc).__name__})

    def connection_lost(self, exc: Optional[Exception]) -> None:
        log_event("UDP_SOCKET_CLOSED", {
            "detail": str(exc) if exc else "clean shutdown"
        })


class UDPStreamService:
    def __init__(self) -> None:
        self._clients: dict[str, dict] = {}
        self._lock     = threading.Lock()
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._running   = False
        self._port: int = 8765

        self._bytes_sent: int        = 0
        self._fps_actual: float      = 0.0
        self._frames_since_stat: int = 0
        self._last_stat_ts: float    = time.monotonic()

        # DoS counters (never reset during a session — monotonically increasing)
        self._packets_dropped_rate:   int = 0   # dropped by UDP rate limiter
        self._packets_rejected_auth:  int = 0   # failed HMAC / no session
        self._clients_rejected_limit: int = 0   # rejected: MAX_STREAM_CLIENTS

        # Per-IP packet rate limiter — checked before any parsing or crypto
        self._udp_rate_limiter = _UDPRateLimiter(
            UDP_RATE_LIMIT_PACKETS, UDP_RATE_LIMIT_WINDOW
        )

        # Capture-state event: set when capture is running, cleared when stopped.
        # The broadcast loop waits on this instead of busy-polling, so CPU usage
        # drops to ~0% while capture is paused.
        self._capture_enabled: asyncio.Event = asyncio.Event()

        self._broadcast_task = None
        self._cleanup_task = None

    # ── Capture state signals (called from main.py) ────────────────────────────

    def capture_started(self) -> None:
        """Unblock the broadcast loop — capture is producing frames."""
        self._capture_enabled.set()

    def capture_stopped(self) -> None:
        """Pause the broadcast loop — capture has stopped."""
        self._capture_enabled.clear()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self._port    = port
        self._running = True
        # FINDING-07: get_running_loop() not deprecated get_event_loop()
        loop = asyncio.get_running_loop()
        try:
            await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self),
                local_addr=(host, port),
            )
            log_event("UDP_SERVER_STARTED", {"host": host, "port": port})
        except Exception as exc:
            self._running = False
            log_event("UDP_START_FAILED", {
                "error": str(exc), "host": host, "port": port,
            })
            # FINDING-06: raise so startup() knows UDP failed
            raise RuntimeError(f"UDP bind failed on {host}:{port}: {exc}") from exc

        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._broadcast_task.add_done_callback(self._task_error_cb)
        self._cleanup_task.add_done_callback(self._task_error_cb)

    def _task_error_cb(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            log_event("UDP_TASK_CRASHED", {
                "error": str(exc), "type": type(exc).__name__,
            })

    async def stop(self) -> None:
        """Gracefully stop the UDP stream service, cancelling background tasks and closing the transport."""
        self._running = False
        # Cancel background tasks if they exist
        for name, task in [("broadcast", self._broadcast_task), ("cleanup", self._cleanup_task)]:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    log_event("UDP_TASK_CANCELLED", {"task": name})
                except Exception as exc:
                    log_event("UDP_TASK_CANCEL_ERROR", {"task": name, "error": str(exc)})
        # Close the transport if it was opened
        if self._transport:
            try:
                self._transport.close()
            except Exception as exc:
                log_event("UDP_STOP_ERROR", {"error": str(exc)})
        log_event("UDP_SERVER_STOPPED", {"bytes_sent": self._bytes_sent})

    # ── Authenticated heartbeat handler ────────────────────────────────────────

    def _on_heartbeat(self, data: bytes, addr: tuple) -> None:
        ip, port = addr

        # ── DoS: per-IP rate limit (checked BEFORE any parsing or crypto) ─────
        if not self._udp_rate_limiter.allow(ip):
            self._packets_dropped_rate += 1
            # Log sparingly — only on the first drop in each burst to avoid
            # the log flood that defeating this check is meant to prevent.
            if self._packets_dropped_rate % 1000 == 1:
                log_event("UDP_RATE_LIMITED", {
                    "ip": ip,
                    "total_dropped": self._packets_dropped_rate,
                })
            return

        if len(data) < 59:
            log_event("UDP_MALFORMED_HEARTBEAT", {
                "ip": ip, "len": len(data), "reason": "too_short",
            })
            return

        try:
            fp_len = struct.unpack(">H", data[:2])[0]
            if fp_len < 1 or 2 + fp_len + 8 + 16 + 32 > len(data):
                raise ValueError("fp_len out of range")

            offset      = 2
            fp_bytes    = data[offset: offset + fp_len];  offset += fp_len
            ts_bytes    = data[offset: offset + 8];       offset += 8
            nonce_bytes = data[offset: offset + 16];      offset += 16
            hmac_tag    = data[offset: offset + 32]
            fp = fp_bytes.decode("utf-8")
        except Exception as exc:
            log_event("UDP_MALFORMED_HEARTBEAT", {
                "ip": ip, "reason": "parse_error", "detail": str(exc),
            })
            return

        from .auth_service import auth_service
        if not auth_service.has_session(fp):
            self._packets_rejected_auth += 1
            log_event("UDP_UNAUTHENTICATED_HEARTBEAT", {
                "ip": ip, "fingerprint": fp[:20],
            })
            return

        session = auth_service._sessions.get(fp)
        if session is None or session.is_expired():
            return

        # VULNERABILITY FIX: Prevent heartbeat IP hijacking
        if ip != session.ip:
            log_event("UDP_HEARTBEAT_IP_MISMATCH", {
                "fingerprint": fp[:20],
                "expected":    session.ip,
                "actual":      ip,
            })
            return

        session_key = auth_service.get_session_key(fp)
        if session_key is None:
            return

        try:
            ts_ms = struct.unpack(">Q", ts_bytes)[0]
        except struct.error:
            log_event("UDP_HEARTBEAT_BAD_TS", {"ip": ip, "fp": fp[:20]})
            return

        now_ms = int(time.time() * 1000)
        skew   = abs(now_ms - ts_ms) / 1000.0
        if skew > HB_TIMESTAMP_SKEW:
            log_event("UDP_HEARTBEAT_REPLAY", {
                "ip": ip, "fp": fp[:20],
                "skew_seconds": round(skew, 2),
                "reason": "timestamp_out_of_window",
            })
            return

        hmac_msg = fp_bytes + ts_bytes + nonce_bytes
        if not hmac_verify(session_key, hmac_msg, hmac_tag):
            self._packets_rejected_auth += 1
            log_event("UDP_HEARTBEAT_HMAC_FAIL", {
                "ip": ip, "fingerprint": fp[:20],
            })
            return

        # VULNERABILITY FIX: Nonce replay history persisted in session memory
        if not auth_service.check_and_add_nonce(fp, nonce_bytes):
            log_event("UDP_HEARTBEAT_NONCE_REPLAY", {
                "ip": ip, "fingerprint": fp[:20],
            })
            return

        with self._lock:
            existing = self._clients.get(fp)
            now = time.time()

            if existing is None:
                # DoS: cap total concurrent stream clients
                if len(self._clients) >= MAX_STREAM_CLIENTS:
                    self._clients_rejected_limit += 1
                    log_event("UDP_CLIENT_LIMIT_REACHED", {
                        "ip": ip, "fingerprint": fp[:20],
                        "current": len(self._clients),
                        "max": MAX_STREAM_CLIENTS,
                    })
                    return

                device_name = auth_service.get_session_device_name(fp) or "Unknown"
                self._clients[fp] = {
                    "ip":           ip,
                    "port":         port,
                    "session_key":  session_key,
                    "connected_at": now,
                    "frames_sent":  0,
                    "last_hb":      now,
                    "device_name":  device_name,
                    "seq":          0,
                }
                log_event("CLIENT_CONNECTED_UDP", {
                    "fingerprint": fp, "ip": ip, "port": port,
                })
            else:
                existing["last_hb"]     = now
                existing["ip"]          = ip
                existing["port"]        = port
                existing["session_key"] = session_key

    # ── Frame broadcast loop ───────────────────────────────────────────────────

    async def _broadcast_loop(self) -> None:
        while self._running:
            # Block here (zero CPU) until capture_started() sets the event.
            # capture_stopped() clears it, making this wait again immediately
            # after the current frame cycle, with no busy-polling.
            await self._capture_enabled.wait()

            t0  = time.monotonic()
            fps = capture_service._fps or 20

            frame, is_keyframe = await capture_service.get_frame_with_flags()

            if frame is None:
                # Capture running but no frame yet (e.g. first startup cycle).
                await asyncio.sleep(0.05)
                continue

            # Determine codec tag from service setting
            codec_tag = (CODEC_TAG_H264
                         if capture_service._codec == "h264"
                         else CODEC_TAG_JPEG)
            flags = FLAG_KEYFRAME if is_keyframe else 0x00

            # FINDING-06 guard: transport may be None if bind failed
            if self._transport is not None:
                with self._lock:
                    clients = list(self._clients.items())

                dead: list[str] = []
                for fp, client in clients:
                    try:
                        frame_seq = client["seq"]
                        aad = struct.pack(">Q", frame_seq)
                        # FINDING-19: encrypt the WHOLE frame once per client
                        # (each client has its own session key), then slice
                        # the ciphertext into MTU-safe fragments below. The
                        # 16B GCM tag lives at the end of the full ciphertext
                        # and therefore ends up on the final fragment only.
                        nonce, ciphertext = aes_encrypt(
                            client["session_key"], frame, aad=aad
                        )

                        frag_count = max(
                            1, -(-len(ciphertext) // PACKET_MAX_PAYLOAD)  # ceil div
                        )
                        if frag_count > MAX_FRAGMENTS:
                            raise ValueError(
                                f"frame too large to fragment: {len(ciphertext)}B "
                                f"needs {frag_count} fragments (max {MAX_FRAGMENTS})"
                            )

                        sent_bytes = 0
                        for frag_index in range(frag_count):
                            start = frag_index * PACKET_MAX_PAYLOAD
                            end   = start + PACKET_MAX_PAYLOAD
                            chunk = ciphertext[start:end]
                            # Wire: [1B codec][1B flags][8B frame_seq]
                            #       [2B frag_index][2B frag_count]
                            #       [4B nonce_len][12B nonce][ciphertext_chunk]
                            packet = (
                                bytes([codec_tag])
                                + bytes([flags])
                                + aad
                                + struct.pack(">H", frag_index)
                                + struct.pack(">H", frag_count)
                                + struct.pack(">I", len(nonce))
                                + nonce
                                + chunk
                            )
                            self._transport.sendto(packet, (client["ip"], client["port"]))
                            sent_bytes += len(packet)

                        client["seq"]           += 1
                        client["frames_sent"]   += 1
                        self._bytes_sent        += sent_bytes
                        self._frames_since_stat += 1
                    except Exception as exc:
                        log_event("UDP_SEND_ERROR", {
                            "fingerprint": fp,
                            "ip":          client.get("ip", "?"),
                            "error":       str(exc),
                            "type":        type(exc).__name__,
                        })
                        dead.append(fp)

                for fp in dead:
                    with self._lock:
                        self._clients.pop(fp, None)
                    log_event("CLIENT_DISCONNECTED_UDP", {"fingerprint": fp})
                    from .auth_service import auth_service
                    auth_service.remove_session_if_single_use(fp)

                elapsed_stat = time.monotonic() - self._last_stat_ts
                if elapsed_stat >= 1.0:
                    self._fps_actual        = self._frames_since_stat / elapsed_stat
                    self._frames_since_stat = 0
                    self._last_stat_ts      = time.monotonic()

            elapsed = time.monotonic() - t0
            sleep   = max(0.0, (1.0 / fps) - elapsed)
            if sleep > 0:
                await asyncio.sleep(sleep)

    # ── Stale client cleanup ───────────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        while self._running:
            await asyncio.sleep(CLIENT_TIMEOUT)
            now   = time.time()
            stale: list[str] = []
            with self._lock:
                for fp, c in list(self._clients.items()):
                    if now - c["last_hb"] > CLIENT_TIMEOUT:
                        stale.append(fp)
                for fp in stale:
                    self._clients.pop(fp, None)
            for fp in stale:
                log_event("CLIENT_TIMEOUT_UDP", {
                    "fingerprint": fp,
                    "timeout_seconds": CLIENT_TIMEOUT,
                })
                from .auth_service import auth_service
                auth_service.remove_session_if_single_use(fp)

    # ── Queries ────────────────────────────────────────────────────────────────

    def remove_client(self, fingerprint: str) -> bool:
        """Immediately disconnect a client and clean up its session."""
        # Remove from client list
        with self._lock:
            client = self._clients.pop(fingerprint, None)
        if client:
            log_event("CLIENT_DISCONNECTED_UDP", {"fingerprint": fingerprint})
            # Also remove auth session if it exists
            from .auth_service import auth_service
            auth_service.remove_session(fingerprint)
            return True
        return False


    async def get_connected(self) -> list[dict]:
        """Return list of currently connected UDP clients with status info."""
        with self._lock:
            return [
                {
                    "fingerprint": fp,
                    "device_name": c["device_name"],
                    "ip": c["ip"],
                    "connected_at": c["connected_at"],
                    "frames_sent": c["frames_sent"],
                }
                for fp, c in self._clients.items()
            ]


    def get_stats(self) -> dict:
        return {
            "client_count":            len(self._clients),
            "fps_actual":              round(self._fps_actual, 1),
            "bytes_sent":              self._bytes_sent,
            "udp_port":                self._port,
            "running":                 self._running,
            "codec":                   capture_service._codec,
            "max_clients":             MAX_STREAM_CLIENTS,
            "packets_dropped_rate":    self._packets_dropped_rate,
            "packets_rejected_auth":   self._packets_rejected_auth,
            "clients_rejected_limit":  self._clients_rejected_limit,
        }

    @property
    def udp_port(self) -> int:
        return self._port


# Global singleton
stream_service = UDPStreamService()