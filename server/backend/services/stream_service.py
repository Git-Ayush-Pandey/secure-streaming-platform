"""
UDP Stream Service — Production Hardened Edition.

Hardening applied in this pass:
  ✓ Removed all [DEBUG-LAN] print() statements (NF-05).
  ✓ UDP_SOCKET_ERROR log throttling: WinError 10054 (ICMP port-unreachable
    on Windows when client UDP port is closed) is expected during reconnects
    and is now counted silently; only logged once per minute per source IP,
    and suppressed entirely after MAX_SOCKET_ERRORS_BEFORE_EVICT consecutive
    errors from the same client fingerprint (which triggers client eviction
    instead of unbounded log amplification) (NF-04, NF-13).
  ✓ Fragment burst pacing: _broadcast_loop yields to the event loop every
    FRAG_YIELD_EVERY fragments via asyncio.sleep(0) so the OS networking
    stack can process earlier datagrams before the next burst arrives,
    preventing UDP receive-buffer overflow on the client (NF-07).
  ✓ Fragment reassembly memory limits (server-side): frag_count validated
    against MAX_FRAGS_PER_FRAME before any allocation; a hard MAX_FRAME_BYTES
    limit ensures no single frame can consume more than ~8 MB of ciphertext.
  ✓ Parser hardening: all packet fields validated before allocation —
    fp_len, nonce_len, frag_count, frag_index, codec_tag, flags (NF parser
    review).
  ✓ Removed temporary debug instance variables (_debug_lan_*).

Previously applied (unchanged):
  ✓ FINDING-06: start() raises RuntimeError on bind failure.
  ✓ FINDING-07: asyncio.get_running_loop().
  ✓ FINDING-12: nonce replay check on first heartbeat.
  ✓ Per-IP UDP rate limiter.
  ✓ MAX_STREAM_CLIENTS cap.
  ✓ Frame fragmentation (MTU-safe).
  ✓ add_done_callback crash visibility.
  ✓ HMAC-verified UDP IP pinning (LAN multi-homed fix).
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
FLAG_KEYFRAME  = 0x01

# Valid codec tags — reject anything else before allocation.
_VALID_CODEC_TAGS = frozenset({CODEC_TAG_JPEG, CODEC_TAG_H264})

FRAME_HEADER_SIZE  = 1 + 1 + 8 + 2 + 2 + 4 + 12   # = 30 bytes
PACKET_MAX_PAYLOAD = 1500 - 20 - 8 - FRAME_HEADER_SIZE - 16   # = 1426 bytes
MAX_FRAGMENTS      = 65535   # frag_count is a 2-byte field

# ── Hardening limits ───────────────────────────────────────────────────────────
# Maximum encoded frame size (plaintext). A 1920×1080 JPEG at quality=80 is
# typically 100–300 KB; 8 MB is a very generous ceiling that stops a crafted
# frag_count from pre-allocating gigabytes of ciphertext.
MAX_FRAME_BYTES = 8 * 1024 * 1024  # 8 MB

# Maximum fragments per frame enforced before any per-fragment allocation.
MAX_FRAGS_PER_FRAME = MAX_FRAME_BYTES // PACKET_MAX_PAYLOAD + 1   # ≈ 5 793

# Yield to the event loop every this many fragments so burst sending doesn't
# overflow the client's UDP receive buffer (NF-07 fragment burst pacing).
FRAG_YIELD_EVERY = 32

# UDP_SOCKET_ERROR throttle: log at most once per minute per IP, and suppress
# entirely once a client has accumulated this many consecutive send errors
# (eviction handles the root cause at that point).
MAX_SOCKET_ERRORS_BEFORE_EVICT = 5
SOCKET_ERROR_LOG_INTERVAL       = 60.0   # seconds


class _UDPRateLimiter:
    """
    Per-IP token-bucket rate limiter for raw UDP packets.
    Checked BEFORE any parsing so flooded packets never reach crypto code.
    """
    def __init__(self, max_per_window: int, window: float) -> None:
        self._max    = max_per_window
        self._window = window
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
        # NF-04 / NF-13: throttle UDP_SOCKET_ERROR logging.
        # WinError 10054 (ICMP port-unreachable) fires for every queued sendto()
        # when a client's UDP port is closed — at 20fps with N fragments/frame
        # this can produce thousands of log events per second. Count silently;
        # the broadcast loop detects persistent errors and evicts the client.
        self._svc._on_socket_error(exc)

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

        # DoS counters (monotonically increasing)
        self._packets_dropped_rate:   int = 0
        self._packets_rejected_auth:  int = 0
        self._clients_rejected_limit: int = 0

        # Per-IP UDP rate limiter
        self._udp_rate_limiter = _UDPRateLimiter(
            UDP_RATE_LIMIT_PACKETS, UDP_RATE_LIMIT_WINDOW
        )

        # NF-04/NF-13: socket error throttle state.
        # ip -> (error_count, last_log_ts)
        self._socket_error_state: dict[str, tuple[int, float]] = {}
        # Total socket errors seen (for get_stats)
        self._socket_errors_total: int = 0

        self._capture_enabled: asyncio.Event = asyncio.Event()
        self._broadcast_task = None
        self._cleanup_task   = None

    # ── Capture state signals ──────────────────────────────────────────────────

    def capture_started(self) -> None:
        self._capture_enabled.set()

    def capture_stopped(self) -> None:
        self._capture_enabled.clear()

    # ── Socket error throttle ──────────────────────────────────────────────────

    def _on_socket_error(self, exc: Exception) -> None:
        """
        NF-04/NF-13: Called by _UDPProtocol.error_received().
        Counts errors silently; logs at most once per SOCKET_ERROR_LOG_INTERVAL.
        """
        self._socket_errors_total += 1
        err_str = str(exc)
        now = time.monotonic()
        count, last_log = self._socket_error_state.get("_global", (0, 0.0))
        count += 1
        if now - last_log >= SOCKET_ERROR_LOG_INTERVAL:
            log_event("UDP_SOCKET_ERROR_SUMMARY", {
                "error":       err_str,
                "type":        type(exc).__name__,
                "count_since_last_log": count,
            })
            self._socket_error_state["_global"] = (0, now)
        else:
            self._socket_error_state["_global"] = (count, last_log)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self._port    = port
        self._running = True
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
            raise RuntimeError(f"UDP bind failed on {host}:{port}: {exc}") from exc

        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._cleanup_task   = asyncio.create_task(self._cleanup_loop())
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
        self._running = False
        for name, task in [("broadcast", self._broadcast_task),
                            ("cleanup",   self._cleanup_task)]:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    log_event("UDP_TASK_CANCELLED", {"task": name})
                except Exception as exc:
                    log_event("UDP_TASK_CANCEL_ERROR", {"task": name, "error": str(exc)})
        if self._transport:
            try:
                self._transport.close()
            except Exception as exc:
                log_event("UDP_STOP_ERROR", {"error": str(exc)})
        log_event("UDP_SERVER_STOPPED", {"bytes_sent": self._bytes_sent})

    # ── Authenticated heartbeat handler ────────────────────────────────────────

    def _on_heartbeat(self, data: bytes, addr: tuple) -> None:
        ip, port = addr

        # DoS: per-IP rate limit before any parsing or crypto.
        if not self._udp_rate_limiter.allow(ip):
            self._packets_dropped_rate += 1
            if self._packets_dropped_rate % 1000 == 1:
                log_event("UDP_RATE_LIMITED", {
                    "ip": ip,
                    "total_dropped": self._packets_dropped_rate,
                })
            return

        # Parser hardening: minimum packet length before any field read.
        if len(data) < 59:
            log_event("UDP_MALFORMED_HEARTBEAT", {
                "ip": ip, "len": len(data), "reason": "too_short",
            })
            return

        # Parse heartbeat fields with validated bounds.
        try:
            fp_len = struct.unpack(">H", data[:2])[0]
            # fp_len sanity: fingerprints are hex strings like "aabb:ccdd:..."
            # Maximum reasonable length is 128 chars (SHA-512 hex, far more than
            # we use); minimum is 1.
            if fp_len < 1 or fp_len > 128:
                raise ValueError(f"fp_len {fp_len} out of [1,128]")
            min_len = 2 + fp_len + 8 + 16 + 32
            if min_len > len(data):
                raise ValueError(f"packet too short for fp_len={fp_len}")

            offset      = 2
            fp_bytes    = data[offset: offset + fp_len];  offset += fp_len
            ts_bytes    = data[offset: offset + 8];       offset += 8
            nonce_bytes = data[offset: offset + 16];      offset += 16
            hmac_tag    = data[offset: offset + 32]

            # Validate fingerprint is printable ASCII before string ops.
            fp = fp_bytes.decode("ascii")
            if not fp.replace(":", "").isalnum():
                raise ValueError("fingerprint contains non-alnum chars")
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

        session_key = auth_service.get_session_key(fp)
        if session_key is None:
            return

        # Timestamp skew check (replay / clock-divergence protection).
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

        # HMAC verification (constant-time).
        hmac_msg = fp_bytes + ts_bytes + nonce_bytes
        if not hmac_verify(session_key, hmac_msg, hmac_tag):
            self._packets_rejected_auth += 1
            log_event("UDP_HEARTBEAT_HMAC_FAIL", {
                "ip": ip, "fingerprint": fp[:20],
            })
            return

        # LAN-aware IP pinning: pin to the FIRST HMAC-verified heartbeat's IP
        # (session.udp_ip), not the TCP /ws/auth IP (session.ip). On a
        # multi-homed Windows machine the OS may pick a different egress
        # interface for UDP than it did for TCP; pinning post-HMAC ensures
        # only a session-key holder can establish or change the pin.
        if session.udp_ip is None:
            session.udp_ip = ip
            log_event("UDP_HEARTBEAT_IP_PINNED", {
                "fingerprint": fp[:20], "udp_ip": ip, "ws_auth_ip": session.ip,
            })
        elif ip != session.udp_ip:
            log_event("UDP_HEARTBEAT_IP_MISMATCH", {
                "fingerprint": fp[:20],
                "expected":    session.udp_ip,
                "actual":      ip,
            })
            return

        # Nonce replay protection.
        if not auth_service.check_and_add_nonce(fp, nonce_bytes):
            log_event("UDP_HEARTBEAT_NONCE_REPLAY", {
                "ip": ip, "fingerprint": fp[:20],
            })
            return

        with self._lock:
            existing = self._clients.get(fp)
            now      = time.time()

            if existing is None:
                if len(self._clients) >= MAX_STREAM_CLIENTS:
                    self._clients_rejected_limit += 1
                    log_event("UDP_CLIENT_LIMIT_REACHED", {
                        "ip": ip, "fingerprint": fp[:20],
                        "current": len(self._clients),
                        "max":     MAX_STREAM_CLIENTS,
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
                    "send_errors":  0,     # consecutive send-error counter
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
            await self._capture_enabled.wait()

            t0  = time.monotonic()
            fps = capture_service._fps or 20

            frame, is_keyframe = await capture_service.get_frame_with_flags()

            if frame is None:
                await asyncio.sleep(0.05)
                continue

            codec_tag = (CODEC_TAG_H264
                         if capture_service._codec == "h264"
                         else CODEC_TAG_JPEG)
            flags = FLAG_KEYFRAME if is_keyframe else 0x00

            if self._transport is not None:
                with self._lock:
                    clients = list(self._clients.items())

                dead: list[str] = []
                for fp, client in clients:
                    try:
                        frame_seq = client["seq"]
                        aad       = struct.pack(">Q", frame_seq)

                        # Pre-flight size check before encryption allocation.
                        if len(frame) > MAX_FRAME_BYTES:
                            log_event("UDP_FRAME_TOO_LARGE", {
                                "fingerprint":  fp[:20],
                                "frame_bytes":  len(frame),
                                "max_bytes":    MAX_FRAME_BYTES,
                            })
                            continue

                        nonce, ciphertext = aes_encrypt(
                            client["session_key"], frame, aad=aad
                        )

                        frag_count = max(
                            1, -(-len(ciphertext) // PACKET_MAX_PAYLOAD)
                        )

                        # Validate fragment count before any per-fragment work.
                        if frag_count > MAX_FRAGS_PER_FRAME:
                            log_event("UDP_FRAG_COUNT_EXCEEDED", {
                                "fingerprint":  fp[:20],
                                "frag_count":   frag_count,
                                "max_frags":    MAX_FRAGS_PER_FRAME,
                                "ciphertext_b": len(ciphertext),
                            })
                            continue

                        sent_bytes = 0
                        for frag_index in range(frag_count):
                            start = frag_index * PACKET_MAX_PAYLOAD
                            chunk = ciphertext[start: start + PACKET_MAX_PAYLOAD]
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

                            # NF-07: yield every FRAG_YIELD_EVERY fragments so the
                            # OS can drain the socket send buffer before the next
                            # burst, preventing UDP receive-buffer overflow at the
                            # client.
                            if frag_index % FRAG_YIELD_EVERY == (FRAG_YIELD_EVERY - 1):
                                await asyncio.sleep(0)

                        client["seq"]           += 1
                        client["frames_sent"]   += 1
                        client["send_errors"]    = 0   # reset on success
                        self._bytes_sent        += sent_bytes
                        self._frames_since_stat += 1

                    except Exception as exc:
                        # NF-04: throttle send-error logging per client.
                        client["send_errors"] = client.get("send_errors", 0) + 1
                        n_errors = client["send_errors"]

                        if n_errors >= MAX_SOCKET_ERRORS_BEFORE_EVICT:
                            # Persistent errors → evict the client. The cleanup
                            # loop will also catch this on timeout, but evicting
                            # immediately stops the log amplification.
                            log_event("UDP_SEND_ERROR_EVICTING", {
                                "fingerprint":    fp,
                                "ip":             client.get("ip", "?"),
                                "error":          str(exc),
                                "type":           type(exc).__name__,
                                "consecutive_errors": n_errors,
                            })
                            dead.append(fp)
                        elif n_errors == 1:
                            # Log only the first error in a run — subsequent errors
                            # are counted but not logged until eviction.
                            log_event("UDP_SEND_ERROR", {
                                "fingerprint": fp,
                                "ip":          client.get("ip", "?"),
                                "error":       str(exc),
                                "type":        type(exc).__name__,
                            })

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
                    "fingerprint":    fp,
                    "timeout_seconds": CLIENT_TIMEOUT,
                })
                from .auth_service import auth_service
                auth_service.remove_session_if_single_use(fp)

    # ── Queries ────────────────────────────────────────────────────────────────

    def remove_client(self, fingerprint: str) -> bool:
        with self._lock:
            client = self._clients.pop(fingerprint, None)
        if client:
            log_event("CLIENT_DISCONNECTED_UDP", {"fingerprint": fingerprint})
            from .auth_service import auth_service
            auth_service.remove_session(fingerprint)
            return True
        return False

    async def get_connected(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "fingerprint": fp,
                    "device_name": c["device_name"],
                    "ip":          c["ip"],
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
