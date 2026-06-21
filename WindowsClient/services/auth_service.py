import json
import base64
import hashlib
import logging
import asyncio
import time
import websockets
from cryptography.hazmat.primitives import serialization
from storage.key_store import load_or_create_keys, public_key_b64
from config.settings import SERVER_IP, AUTH_PORT, DEVICE_ID, DEVICE_NAME
from .crypto_service import (
    generate_x25519_keypair, x25519_exchange, derive_session_key,
    verify_server_signature
)
from .trust_store import verify_or_save_server

logger = logging.getLogger("AuthService")

class SecurityError(Exception):
    """Custom exception raised when server verification or signature check fails."""
    pass

class AuthService:
    def __init__(self):
        self.session_key = None
        self.fingerprint = None
        self.state_callback = None
        self.ws_connection = None

    def set_state_callback(self, cb):
        self.state_callback = cb

    def _notify(self, state, details=None):
        if self.state_callback:
            self.state_callback(state, details)

    async def authenticate(self):
        self._notify("AUTHENTICATING", "Loading identity keys")
        priv, pub = load_or_create_keys()
        
        raw_pub = pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        digest = hashlib.sha256(raw_pub).hexdigest()
        self.fingerprint = ":".join(digest[i:i+4] for i in range(0, 32, 4))
        
        # Ephemeral X25519 keys
        x_priv, x_pub = generate_x25519_keypair()
        x_pub_bytes = x_pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        x_pub_b64 = base64.b64encode(x_pub_bytes).decode()
        
        ws_url = f"ws://{SERVER_IP}:{AUTH_PORT}/ws/auth"
        logger.info(f"Connecting to authentication server at {ws_url}")
        
        self.ws_connection = await websockets.connect(ws_url)
        try:
            hello = {
                "type": "HELLO",
                "device_id": DEVICE_ID,
                "device_name": DEVICE_NAME,
                "public_key_b64": public_key_b64(pub),
                "x25519_public_b64": x_pub_b64
            }
            
            logger.info("Sending HELLO message")
            await self.ws_connection.send(json.dumps(hello))
            
            raw_reply = await self.ws_connection.recv()
            reply = json.loads(raw_reply)
            
            status = reply.get("status")
            logger.info(f"Received HELLO response: status={status}")
            
            if status == "blocked":
                self._notify("BLOCKED", "Device is blocked by operator")
                raise PermissionError("Connection rejected: Device is blocked by server operator")
                
            if status == "pending":
                self._notify("PENDING_APPROVAL", "Waiting for operator approval...")
                logger.info("Device is pending operator approval. Starting heartbeat ping loop.")
                
                # We need to wait for the server to push the challenge.
                # While waiting, we send a PING every 10s to keep the challenge from expiring (GC).
                reply_event = asyncio.Event()
                challenge_reply = {}
                
                async def ping_loop():
                    try:
                        while not reply_event.is_set():
                            await asyncio.sleep(10)
                            logger.debug("Sending WebSocket PING to keep pending challenge alive")
                            await self.ws_connection.send(json.dumps({"type": "PING"}))
                    except Exception as e:
                        logger.error(f"Ping loop error: {e}")
                
                ping_task = asyncio.create_task(ping_loop())
                
                try:
                    while True:
                        msg_raw = await self.ws_connection.recv()
                        msg = json.loads(msg_raw)
                        
                        # Handle PONG response
                        if msg.get("type") == "PONG":
                            continue
                            
                        # Handle challenge pushed by operator approval
                        if msg.get("status") == "challenge":
                            challenge_reply.update(msg)
                            reply_event.set()
                            break
                            
                        if msg.get("status") == "blocked":
                            self._notify("BLOCKED", "Device is blocked by operator")
                            raise PermissionError("Connection rejected: Device is blocked by server operator")
                            
                        if msg.get("status") == "rejected":
                            raise PermissionError("Connection rejected: Connection rejected by operator")
                            
                        if msg.get("status") == "error":
                            raise RuntimeError(f"Server error: {msg.get('message')}")
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass
                        
                reply = challenge_reply
            elif status == "rate_limited":
                self._notify("RATE_LIMITED", reply.get("message", "Too many requests"))
                raise ConnectionError(f"Authentication rate limited: {reply.get('message')}")
            elif status == "error":
                raise RuntimeError(f"Handshake error: {reply.get('message')}")
            elif status != "challenge":
                raise RuntimeError(f"Unexpected response status: {status}")
                
            # Now we have the challenge
            self._notify("VERIFYING_SERVER", "Verifying server signature")
            challenge = base64.b64decode(reply["challenge_b64"])
            srv_x_pub_b64 = reply["server_x25519_public_b64"]
            srv_x_pub_bytes = base64.b64decode(srv_x_pub_b64)
            server_fp = reply["server_fingerprint"]
            server_pub_b64 = reply["server_public_key_b64"]
            server_pub_bytes = base64.b64decode(server_pub_b64)
            
            # The server signs: challenge + client_x25519_pub_bytes + server_x25519_pub_bytes
            server_sig_b64 = reply.get("server_signature_b64")
            if not server_sig_b64:
                self._notify("AUTH_FAILED", "Missing server signature")
                raise SecurityError("Security breach: Server did not sign the challenge response.")
            server_sig = base64.b64decode(server_sig_b64)
            
            # Verify server fingerprint using trust store
            if not verify_or_save_server(server_fp):
                self._notify("MITM_WARNING", "Server fingerprint verification failed!")
                raise SecurityError("Security breach: Server fingerprint mismatch! Possible MITM attack.")
                
            # Verify server's signature over binding_msg
            binding_msg = challenge + x_pub_bytes + srv_x_pub_bytes
            if not verify_server_signature(server_pub_bytes, binding_msg, server_sig):
                self._notify("AUTH_FAILED", "Server signature verification failed")
                raise SecurityError("Security breach: Server signature verification failed.")
                
            # Sign challenge to authenticate client
            logger.info("Server verified. Signing challenge binding.")
            client_sig = priv.sign(binding_msg)
            
            # Send challenge response
            await self.ws_connection.send(json.dumps({
                "type": "CHALLENGE_RESPONSE",
                "fingerprint": self.fingerprint,
                "signature_b64": base64.b64encode(client_sig).decode()
            }))
            
            logger.info("Sent CHALLENGE_RESPONSE")
            
            # Receive authenticated reply
            auth_reply_raw = await self.ws_connection.recv()
            auth_reply = json.loads(auth_reply_raw)
            
            if auth_reply.get("status") != "authenticated":
                self._notify("AUTH_FAILED", auth_reply.get("message", "Rejected"))
                raise PermissionError(f"Authentication failed: {auth_reply.get('message')}")
                
            logger.info("Successfully authenticated with server!")
            self._notify("CONNECTED", "Authentication complete")
            
            # Calculate clock offset with server to compensate for LAN clock skew
            server_time_ms = auth_reply.get("server_time_ms")
            if server_time_ms is not None:
                client_time_ms = int(time.time() * 1000)
                self.clock_offset_ms = server_time_ms - client_time_ms
                logger.info(f"Calculated clock offset with server: {self.clock_offset_ms} ms")
            else:
                self.clock_offset_ms = 0
            
            # Derive shared AES key
            shared = x25519_exchange(x_priv, srv_x_pub_bytes)
            self.session_key = derive_session_key(shared, salt=challenge)
            
            return self.session_key, auth_reply["udp_port"]
            
        except Exception:
            await self.disconnect()
            raise

    async def disconnect(self):
        if self.ws_connection:
            try:
                await self.ws_connection.close()
            except Exception:
                pass
            self.ws_connection = None