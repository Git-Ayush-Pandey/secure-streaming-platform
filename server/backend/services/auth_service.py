"""
Authentication Service — Hardened + Fixes Edition.

Fixes applied:
  ✓ FINDING-03: AuthService tracks per-fingerprint auth WebSocket; approve/
    allow_once push a challenge directly to the waiting client.
  ✓ FINDING-04: remove_session_if_single_use called on auth WS disconnect for
    single-use sessions.
  ✓ FINDING-16: GC interval reduced to CHALLENGE_TTL (60s) so expired
    challenges are pruned within one TTL cycle, not up to 2×.
  ✓ Rate-limiter bucket pruning: buckets with all timestamps outside the window
    are removed periodically to prevent unbounded memory growth.
  ✓ Session revocation on trust removal (remove_session called from registry).
"""
from __future__ import annotations

import asyncio
import base64
import time
from collections import deque
from typing import Callable, Optional

from .crypto_service import (
    fingerprint_from_raw_b64, verify, generate_challenge,
    generate_x25519_keypair, x25519_exchange, derive_session_key,
    public_key_from_raw,
)
from . import device_registry as reg
from .logger import log_event

# ── Security constants ────────────────────────────────────────────────────────
from ..settings import (
    CHALLENGE_TTL,
    SESSION_TTL,
    MAX_PENDING_DEVICES as MAX_PENDING,
    AUTH_RATE_LIMIT_WINDOW as RATE_LIMIT_WINDOW,
    AUTH_RATE_LIMIT_MAX as RATE_LIMIT_MAX,
    PENDING_FP_WINDOW,
    PENDING_FP_MAX,
    SESSION_GC_INTERVAL,
)

# Per-IP limit on new unknown fingerprints entering the pending queue.
# This bounds the rate at which an attacker can flood the queue with fresh
# key pairs to evict legitimate pending requests from other IPs.
# Trusted and blocked devices are exempt (they never touch the pending queue).

class PendingRequest:
    __slots__ = (
        "device_id", "device_name", "fingerprint", "public_key_b64",
        "ip", "timestamp", "challenge", "challenge_expires",
        "x25519_server_priv", "client_x25519_pub_bytes", "allow_once",
        "auth_ws",          # FINDING-03: reference to waiting WebSocket
    )

    def __init__(self, device_id, device_name, fingerprint, public_key_b64,
                 ip, client_x25519_pub_bytes=None, auth_ws=None):
        self.device_id    = device_id
        self.device_name  = device_name
        self.fingerprint  = fingerprint
        self.public_key_b64 = public_key_b64
        self.ip           = ip
        self.timestamp    = time.time()
        self.challenge    = generate_challenge()
        self.challenge_expires = self.timestamp + CHALLENGE_TTL
        self.x25519_server_priv, _ = generate_x25519_keypair()
        self.client_x25519_pub_bytes = client_x25519_pub_bytes
        self.allow_once   = False
        self.auth_ws      = auth_ws     # FINDING-03

    def challenge_expired(self):
        return time.time() > self.challenge_expires

    def refresh(self, client_x25519_pub_bytes=None, auth_ws=None):
        self.challenge         = generate_challenge()
        self.challenge_expires = time.time() + CHALLENGE_TTL
        self.x25519_server_priv, _ = generate_x25519_keypair()
        if client_x25519_pub_bytes:
            self.client_x25519_pub_bytes = client_x25519_pub_bytes
        if auth_ws is not None:
            self.auth_ws = auth_ws


class _Session:
    __slots__ = ("key", "expires_at", "device_name", "ip", "single_use", "auth_ws", "used_nonces")

    def __init__(self, key, device_name, ip, single_use: bool = False, auth_ws=None):
        self.key         = key
        self.expires_at  = time.time() + SESSION_TTL
        self.device_name = device_name
        self.ip          = ip
        self.single_use  = single_use
        self.auth_ws     = auth_ws   # FINDING-04
        self.used_nonces = deque(maxlen=256)

    def is_expired(self):
        return time.time() > self.expires_at


class _RateLimiter:
    def __init__(self, window, max_requests):
        self._window = window
        self._max    = max_requests
        self._buckets: dict[str, deque] = {}

    def allow(self, ip: str) -> bool:
        now    = time.time()
        bucket = self._buckets.setdefault(ip, deque())
        while bucket and bucket[0] < now - self._window:
            bucket.popleft()
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True

    def prune(self) -> None:
        """Remove buckets where all timestamps are outside the window."""
        now    = time.time()
        cutoff = now - self._window
        dead   = [ip for ip, q in self._buckets.items()
                  if not q or q[-1] < cutoff]
        for ip in dead:
            del self._buckets[ip]


class AuthService:
    def __init__(self):
        self._pending: dict[str, PendingRequest] = {}
        self._pending_order: deque[str]           = deque()
        self._sessions: dict[str, _Session]       = {}
        self._callbacks: list[Callable]           = []
        self._limiter         = _RateLimiter(RATE_LIMIT_WINDOW, RATE_LIMIT_MAX)
        # Separate, stricter limiter just for new-fingerprint pending insertions
        self._pending_fp_limiter = _RateLimiter(PENDING_FP_WINDOW, PENDING_FP_MAX)
        
        self._server_private = None
        self._server_public = None
        self._server_fp = ""
        self._gc_task = None

    def set_server_keys(self, private_key, public_key, fingerprint: str) -> None:
        self._server_private = private_key
        self._server_public = public_key
        self._server_fp = fingerprint

    def refresh_pending(self, fingerprint: str) -> None:
        req = self._pending.get(fingerprint)
        if req:
            req.challenge_expires = time.time() + CHALLENGE_TTL

    def check_and_add_nonce(self, fingerprint: str, nonce: bytes) -> bool:
        s = self._sessions.get(fingerprint)
        if not s or s.is_expired():
            return False
        if nonce in s.used_nonces:
            return False
        s.used_nonces.append(nonce)
        return True

    def get_session_device_name(self, fingerprint: str) -> Optional[str]:
        s = self._sessions.get(fingerprint)
        if s and not s.is_expired():
            return s.device_name
        return None

    # ── Callback ───────────────────────────────────────────────────────────────

    def register_pending_callback(self, cb: Callable):
        self._callbacks.append(cb)

    def _notify_pending(self, req: PendingRequest):
        for cb in self._callbacks:
            try:
                cb(req)
            except Exception as exc:
                log_event("CALLBACK_ERROR", {"error": str(exc)})

    # ── Background GC ──────────────────────────────────────────────────────────

    async def start_gc(self):
        self._gc_task = asyncio.create_task(self._gc_loop())
        self._gc_task.add_done_callback(self._gc_error_cb)

    def _gc_error_cb(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            log_event("GC_TASK_CRASHED", {"error": str(exc), "type": type(exc).__name__})

    async def _gc_loop(self):
        while True:
            await asyncio.sleep(SESSION_GC_INTERVAL)
            self._gc_sessions()
            self._gc_challenges()
            self._limiter.prune()            # Rate-limiter bucket pruning
            self._pending_fp_limiter.prune() # Pending-FP rate-limiter pruning

    def _gc_sessions(self):
        expired = [fp for fp, s in self._sessions.items() if s.is_expired()]
        for fp in expired:
            del self._sessions[fp]
            log_event("SESSION_EXPIRED", {"fingerprint": fp})

    def _gc_challenges(self):
        expired = [fp for fp, r in self._pending.items() if r.challenge_expired()]
        for fp in expired:
            req = self._pending.pop(fp, None)
            try:
                self._pending_order.remove(fp)
            except ValueError:
                pass
            if req:
                log_event("CHALLENGE_EXPIRED", {
                    "fingerprint": fp, "ip": req.ip,
                    "device_name": req.device_name,
                })

    # ── HELLO ──────────────────────────────────────────────────────────────────

    def handle_hello(self, device_id: str, device_name: str,
                     public_key_b64: str, ip: str,
                     client_x25519_pub_b64: Optional[str] = None,
                     auth_ws=None) -> dict:
        if not self._limiter.allow(ip):
            log_event("RATE_LIMIT_EXCEEDED", {"ip": ip, "device_id": device_id})
            return {"status": "rate_limited", "challenge_b64": None, "session_key_b64": None}

        fp = fingerprint_from_raw_b64(public_key_b64)

        if not client_x25519_pub_b64:
            log_event("AUTH_FAILURE", {
                "fingerprint": fp, "ip": ip,
                "reason": "missing_x25519_public_key",
            })
            return {"status": "error",
                    "message": "X25519 public key required"}

        try:
            client_x25519_bytes = base64.b64decode(client_x25519_pub_b64)
        except Exception:
            log_event("AUTH_FAILURE", {
                "fingerprint": fp, "ip": ip, "reason": "invalid_x25519_encoding",
            })
            return {"status": "error", "message": "Invalid X25519 key encoding"}

        if reg.get_blocked(fp):
            log_event("CLIENT_REJECTED", {
                "fingerprint": fp, "ip": ip, "reason": "blocked",
            })
            reg.save_rejected(device_id, fp, ip, "Device is blocked", device_name)
            return {"status": "blocked", "challenge_b64": None, "session_key_b64": None}

        if reg.get_trusted(fp):
            return self._issue_challenge(
                device_id, device_name, fp, public_key_b64,
                ip, client_x25519_bytes, auth_ws=auth_ws,
            )

        # Unknown → pending queue — check per-IP new-fingerprint rate first
        if not self._pending_fp_limiter.allow(ip):
            log_event("PENDING_FP_RATE_LIMITED", {
                "ip": ip, "fingerprint": fp[:20], "device_id": device_id,
                "reason": f">{PENDING_FP_MAX} new fingerprints/{PENDING_FP_WINDOW}s from this IP",
            })
            return {"status": "rate_limited",
                    "message": "Too many new device registrations from your IP"}

        if len(self._pending) >= MAX_PENDING:
            oldest_fp = self._pending_order.popleft()
            evicted   = self._pending.pop(oldest_fp, None)
            if evicted:
                log_event("PENDING_EVICTED", {
                    "fingerprint": oldest_fp,
                    "device_name": evicted.device_name,
                    "reason": "queue_full",
                })

        req = PendingRequest(device_id, device_name, fp,
                             public_key_b64, ip, client_x25519_bytes,
                             auth_ws=auth_ws)
        self._pending[fp] = req
        self._pending_order.append(fp)

        log_event("PENDING_REQUEST", {
            "fingerprint": fp, "ip": ip, "device_name": device_name,
        })
        self._notify_pending(req)
        reg.save_recent(device_id, fp, ip, "pending", device_name)
        return {"status": "pending", "challenge_b64": None, "session_key_b64": None}

    def _issue_challenge(self, device_id, device_name, fp, pub_b64,
                         ip, client_x25519_bytes, auth_ws=None):
        existing = self._pending.get(fp)
        if existing and existing.challenge_expired():
            existing = None

        if existing is None:
            req = PendingRequest(device_id, device_name, fp,
                                 pub_b64, ip, client_x25519_bytes,
                                 auth_ws=auth_ws)
            self._pending[fp] = req
            if fp not in self._pending_order:
                self._pending_order.append(fp)
        else:
            req = existing
            req.refresh(client_x25519_bytes, auth_ws=auth_ws)

        response: dict = {
            "status": "challenge",
            "challenge_b64": base64.b64encode(req.challenge).decode(),
            "session_key_b64": None,
        }

        if req.client_x25519_pub_bytes:
            from cryptography.hazmat.primitives import serialization as _ser
            srv_pub_bytes = req.x25519_server_priv.public_key().public_bytes(
                _ser.Encoding.Raw, _ser.PublicFormat.Raw,
            )
            response["server_x25519_public_b64"] = base64.b64encode(srv_pub_bytes).decode()

            if self._server_private:
                binding_msg = req.challenge + req.client_x25519_pub_bytes + srv_pub_bytes
                sig = self._server_private.sign(binding_msg)
                response["server_signature_b64"] = base64.b64encode(sig).decode()
                response["server_public_key_b64"] = base64.b64encode(
                    self._server_public.public_bytes(
                        _ser.Encoding.Raw, _ser.PublicFormat.Raw
                    )
                ).decode()
                response["server_fingerprint"] = self._server_fp

        return response

    # ── CHALLENGE_RESPONSE ─────────────────────────────────────────────────────

    def verify_challenge(self, fingerprint: str, signature_b64: str) -> dict:
        req = self._pending.get(fingerprint)
        if not req:
            log_event("AUTH_FAILURE", {
                "fingerprint": fingerprint, "reason": "no_pending_challenge",
            })
            return {"status": "error", "message": "No pending challenge — reconnect required"}

        if req.challenge_expired():
            self._pending.pop(fingerprint, None)
            try:
                self._pending_order.remove(fingerprint)
            except ValueError:
                pass
            log_event("AUTH_FAILURE", {
                "fingerprint": fingerprint, "ip": req.ip,
                "reason": "challenge_expired",
            })
            return {"status": "error", "message": "Challenge expired — reconnect required"}

        try:
            raw_pub = base64.b64decode(req.public_key_b64)
            pub     = public_key_from_raw(raw_pub)
            sig     = base64.b64decode(signature_b64)
        except Exception as exc:
            log_event("AUTH_FAILURE", {
                "fingerprint": fingerprint, "ip": req.ip,
                "reason": "decode_error", "detail": str(exc),
            })
            return {"status": "error", "message": "Encoding error in challenge response"}

        from cryptography.hazmat.primitives import serialization as _ser
        srv_pub_bytes = req.x25519_server_priv.public_key().public_bytes(
            _ser.Encoding.Raw, _ser.PublicFormat.Raw,
        )
        binding_msg = req.challenge + req.client_x25519_pub_bytes + srv_pub_bytes

        if not verify(pub, binding_msg, sig):
            log_event("AUTH_FAILURE", {
                "fingerprint": fingerprint, "ip": req.ip,
                "reason": "bad_signature",
            })
            reg.save_rejected(req.device_id, fingerprint, req.ip,
                               "Signature verification failed", req.device_name)
            return {"status": "error", "message": "Signature verification failed"}

        try:
            shared   = x25519_exchange(req.x25519_server_priv,
                                       req.client_x25519_pub_bytes)
            sess_key = derive_session_key(shared, salt=req.challenge)
        except Exception as exc:
            log_event("AUTH_FAILURE", {
                "fingerprint": fingerprint, "ip": req.ip,
                "reason": "x25519_kdf_failure", "detail": str(exc),
            })
            return {"status": "error", "message": "Key derivation failed"}

        # Store session; retain auth_ws for single-use revocation (FINDING-04)
        self._sessions[fingerprint] = _Session(
            sess_key, req.device_name, req.ip,
            single_use=req.allow_once,
            auth_ws=req.auth_ws,
        )

        reg.update_trusted_stats(fingerprint, req.ip)
        reg.save_recent(req.device_id, fingerprint, req.ip,
                        "connected", req.device_name)
        log_event("CLIENT_AUTHENTICATED", {
            "fingerprint": fingerprint,
            "device_name": req.device_name,
            "ip":          req.ip,
            "method":      "x25519_hkdf",
        })

        self._pending.pop(fingerprint, None)
        try:
            self._pending_order.remove(fingerprint)
        except ValueError:
            pass

        return {"status": "authenticated", "session_key_b64": None}

    # ── Dashboard actions ──────────────────────────────────────────────────────

    async def approve_permanently(self, fingerprint: str) -> bool:
        req = self._pending.get(fingerprint)
        if not req:
            return False
        reg.save_trusted({
            "device_id":      req.device_id,
            "device_name":    req.device_name,
            "fingerprint":    fingerprint,
            "public_key_b64": req.public_key_b64,
            "last_ip":        req.ip,
        })
        log_event("CLIENT_TRUSTED", {
            "fingerprint": fingerprint, "device_name": req.device_name,
        })
        # FINDING-03: push challenge to the waiting client
        await self._push_challenge_to_client(fingerprint)
        return True

    async def allow_once(self, fingerprint: str) -> bool:
        req = self._pending.get(fingerprint)
        if not req:
            return False
        req.allow_once = True
        log_event("ALLOW_ONCE", {"fingerprint": fingerprint, "ip": req.ip})
        # FINDING-03: push challenge to the waiting client
        await self._push_challenge_to_client(fingerprint)
        return True

    async def _push_challenge_to_client(self, fingerprint: str) -> None:
        """
        FINDING-03: After approve/allow_once, issue a fresh challenge to the
        client's auth WebSocket if it is still connected.
        """
        req = self._pending.get(fingerprint)
        if not req or req.auth_ws is None:
            return
        if req.challenge_expired():
            return

        import json
        from cryptography.hazmat.primitives import serialization as _ser
        srv_pub_bytes = req.x25519_server_priv.public_key().public_bytes(
            _ser.Encoding.Raw, _ser.PublicFormat.Raw,
        )
        binding_msg = req.challenge + req.client_x25519_pub_bytes + srv_pub_bytes
        msg = {
            "status":                  "challenge",
            "challenge_b64":           base64.b64encode(req.challenge).decode(),
            "server_x25519_public_b64": base64.b64encode(srv_pub_bytes).decode(),
            "session_key_b64":         None,
        }
        
        if self._server_private:
            sig = self._server_private.sign(binding_msg)
            msg["server_signature_b64"] = base64.b64encode(sig).decode()
            msg["server_public_key_b64"] = base64.b64encode(
                self._server_public.public_bytes(
                    _ser.Encoding.Raw, _ser.PublicFormat.Raw
                )
            ).decode()
            msg["server_fingerprint"] = self._server_fp

        try:
            await req.auth_ws.send_text(json.dumps(msg))
        except Exception as exc:
            log_event("CHALLENGE_PUSH_FAILED", {
                "fingerprint": fingerprint, "error": str(exc),
            })

    async def reject(self, fingerprint: str) -> bool:
        req = self._pending.pop(fingerprint, None)
        try:
            self._pending_order.remove(fingerprint)
        except ValueError:
            pass
        if not req:
            return False

        if req.auth_ws:
            try:
                import json
                await req.auth_ws.send_text(json.dumps({
                    "status": "rejected",
                    "message": "Connection rejected by operator"
                }))
                await req.auth_ws.close()
            except Exception:
                pass

        reg.save_rejected(req.device_id, fingerprint, req.ip,
                           "Manually rejected", req.device_name)
        log_event("CLIENT_REJECTED", {
            "fingerprint": fingerprint, "ip": req.ip,
            "reason": "manual_reject",
        })
        return True

    async def block_permanently(self, fingerprint: str) -> bool:
        req = self._pending.pop(fingerprint, None)
        try:
            self._pending_order.remove(fingerprint)
        except ValueError:
            pass
        data: dict = {}
        if req:
            data = {
                "device_id":      req.device_id,
                "device_name":    req.device_name,
                "fingerprint":    fingerprint,
                "public_key_b64": req.public_key_b64,
                "last_ip":        req.ip,
            }
            if req.auth_ws:
                try:
                    import json
                    await req.auth_ws.send_text(json.dumps({
                        "status": "blocked",
                        "message": "Device is blocked by operator"
                    }))
                    await req.auth_ws.close()
                except Exception:
                    pass
        else:
            trusted = reg.get_trusted(fingerprint)
            if trusted:
                data = {**trusted, "fingerprint": fingerprint}
        if data:
            reg.save_blocked(data)
            self._sessions.pop(fingerprint, None)
            log_event("CLIENT_BLOCKED", {
                "fingerprint": fingerprint,
                "device_name": data.get("device_name", "unknown"),
            })
            return True
        return False

    # ── Queries ────────────────────────────────────────────────────────────────

    def has_session(self, fingerprint: str) -> bool:
        s = self._sessions.get(fingerprint)
        if s is None:
            return False
        if s.is_expired():
            del self._sessions[fingerprint]
            log_event("SESSION_EXPIRED", {"fingerprint": fingerprint})
            return False
        return True

    def get_session_key(self, fingerprint: str) -> Optional[bytes]:
        s = self._sessions.get(fingerprint)
        if s and not s.is_expired():
            return s.key
        return None

    def remove_session(self, fingerprint: str):
        self._sessions.pop(fingerprint, None)

    def remove_session_if_single_use(self, fingerprint: str) -> None:
        s = self._sessions.get(fingerprint)
        if s and s.single_use:
            self._sessions.pop(fingerprint, None)
            log_event("SINGLE_USE_SESSION_REMOVED", {"fingerprint": fingerprint})

    # FINDING-04: called from auth WS on disconnect
    def on_auth_ws_disconnect(self, fingerprint: str) -> None:
        self.remove_session_if_single_use(fingerprint)

    def get_pending_list(self) -> list[dict]:
        now = time.time()
        return [
            {
                "device_id":   r.device_id,
                "device_name": r.device_name,
                "fingerprint": r.fingerprint,
                "ip":          r.ip,
                "timestamp":   r.timestamp,
                "expires_in":  max(0.0, r.challenge_expires - now),
            }
            for r in self._pending.values()
            if not r.challenge_expired()
        ]


# Global singleton
auth_service = AuthService()