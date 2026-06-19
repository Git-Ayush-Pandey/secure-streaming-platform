import asyncio
import logging
import socket
import time
from typing import Optional, Callable
import numpy as np

from config.settings import SERVER_IP
from .state_machine import StateMachine
from .retry_policy import RetryPolicy
from .lifecycle import Lifecycle
from services.auth_service import AuthService, SecurityError
from services.transport import start_udp_receiver
from services.heartbeat import send_heartbeat
from services.frame_reassembler import FrameReassembler
from services.decoder import VideoDecoder

logger = logging.getLogger("ConnectionManager")

class ConnectionManager:
    def __init__(self):
        self.state_machine = StateMachine()
        self.retry_policy = RetryPolicy()
        self.lifecycle = Lifecycle()
        self.auth_service = AuthService()
        
        self.auth_service.set_state_callback(self._on_auth_state_change)
        
        self.session_key: Optional[bytes] = None
        self.server_udp_port: int = 8765
        
        self.udp_transport: Optional[asyncio.DatagramTransport] = None
        self.packet_queue = asyncio.Queue(maxsize=1000)
        self.frame_reassembler = FrameReassembler()
        self.decoder = VideoDecoder()
        
        self.last_frame_time = 0.0
        self.frame_callback: Optional[Callable[[np.ndarray, bool], None]] = None
        
        self._connection_task = None
        self._running = False

    def set_frame_callback(self, cb: Callable[[np.ndarray, bool], None]):
        self.frame_callback = cb

    def _on_auth_state_change(self, state: str, details: Optional[str] = None):
        """Map AuthService internal transitions directly to StateMachine."""
        if state == "AUTHENTICATING":
            self.state_machine.transition_to(StateMachine.AUTHENTICATING, details)
        elif state == "PENDING_APPROVAL":
            self.state_machine.transition_to(StateMachine.PENDING_APPROVAL, details)
        elif state == "BLOCKED":
            self.state_machine.transition_to(StateMachine.BLOCKED, details)
        elif state == "CONNECTED":
            # Will be fully set connected once UDP is up
            pass
        elif state == "AUTH_FAILED":
            self.state_machine.transition_to(StateMachine.ERROR, details)

    async def start(self):
        """Start the connection manager loop."""
        if self._running:
            return
        self._running = True
        self._connection_task = asyncio.create_task(self._main_loop())
        self.lifecycle.track_task(self._connection_task)

    async def stop(self):
        """Stop connection manager and clean up resources."""
        self._running = False
        if self._connection_task:
            self._connection_task.cancel()
        await self._cleanup_connection()
        await self.lifecycle.shutdown()

    async def _main_loop(self):
        """Main orchestrator loop handling connection establishment and automatic retries."""
        while self._running and not self.lifecycle.is_shutting_down:
            try:
                self.state_machine.transition_to(StateMachine.CONNECTING, "Starting connection handshake")
                
                # 1. Complete WS authentication handshake and exchange keys
                self.session_key, self.server_udp_port = await self.auth_service.authenticate()
                self.frame_reassembler = FrameReassembler() # Reset reassembler sequence counters
                
                # 2. Setup shared UDP receiver socket and start receiver protocol
                # Bind to port 0 for dynamic client ephemeral port assignment
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("0.0.0.0", 0))
                sock.setblocking(False)
                client_port = sock.getsockname()[1]
                logger.info(f"UDP socket bound to client ephemeral port: {client_port}")
                
                self.udp_transport = await start_udp_receiver(0, self.packet_queue, sock=sock)
                
                self.state_machine.transition_to(StateMachine.CONNECTED, f"Stream connected via server UDP port {self.server_udp_port}")
                self.retry_policy.reset()
                self.last_frame_time = time.time()
                
                # 3. Launch heartbeat loop, packet processing, and connection timeout guard tasks
                hb_task = asyncio.create_task(self._heartbeat_loop(sock))
                rx_task = asyncio.create_task(self._packet_process_loop())
                timeout_task = asyncio.create_task(self._timeout_guard_loop())
                
                self.lifecycle.track_task(hb_task)
                self.lifecycle.track_task(rx_task)
                self.lifecycle.track_task(timeout_task)
                
                # Wait until one of the loops exits or connection fails
                done, pending = await asyncio.wait(
                    [hb_task, rx_task, timeout_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                
                # Extract exception from completed tasks if any
                for task in done:
                    exc = task.exception()
                    if exc and not isinstance(exc, asyncio.CancelledError):
                        raise exc
                        
            except SecurityError as e:
                # Fatal security issues (e.g., MITM or verify signature failure) -> abort
                logger.critical(f"Security error: {e}")
                self.state_machine.transition_to(StateMachine.BLOCKED, f"Security Violation: {e}")
                break
            except PermissionError as e:
                # Device is blocked on server -> do not retry immediately
                logger.warning(f"Access denied: {e}")
                self.state_machine.transition_to(StateMachine.BLOCKED, str(e))
                await asyncio.sleep(10) # check again after 10s
            except Exception as e:
                logger.error(f"Connection error: {e}")
                self.state_machine.transition_to(StateMachine.ERROR, str(e))
                
            # Clean up current connection states
            await self._cleanup_connection()
            
            # Apply backoff retry
            if self._running:
                delay = self.retry_policy.get_delay()
                logger.info(f"Reconnecting in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

    async def _cleanup_connection(self):
        """Shutdown transport channels and clear buffers."""
        if self.udp_transport:
            try:
                self.udp_transport.close()
            except Exception:
                pass
            self.udp_transport = None
            
        # Drain packet queue
        while not self.packet_queue.empty():
            try:
                self.packet_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
        self.session_key = None

    async def _heartbeat_loop(self, sock: socket.socket):
        """Send authenticated UDP heartbeats to the server every 5 seconds."""
        while self.state_machine.state == StateMachine.CONNECTED:
            send_heartbeat(
                sock=sock,
                server_ip=SERVER_IP,
                server_port=self.server_udp_port,
                fingerprint=self.auth_service.fingerprint,
                session_key=self.session_key
            )
            await asyncio.sleep(5)

    async def _packet_process_loop(self):
        """Dequeue UDP packets, reassemble slices, decrypt, and decode frame bytes."""
        while self.state_machine.state == StateMachine.CONNECTED:
            data, addr = await self.packet_queue.get()
            
            # process packet
            res = self.frame_reassembler.process_packet(data, self.session_key)
            if res:
                decrypted_bytes, codec_tag, is_keyframe = res
                self.last_frame_time = time.time()
                
                # decode frame
                frame = self.decoder.decode(decrypted_bytes, codec_tag)
                if frame is not None:
                    if self.frame_callback:
                        try:
                            self.frame_callback(frame, is_keyframe)
                        except Exception as e:
                            logger.error(f"Frame callback crashed: {e}")

    async def _timeout_guard_loop(self):
        """Monitor incoming stream activity. Trigger reconnect on 15s timeout."""
        while self.state_machine.state == StateMachine.CONNECTED:
            await asyncio.sleep(2)
            if time.time() - self.last_frame_time > 15.0:
                logger.warning("UDP stream receipt timed out (no packets received for 15s). Reconnecting.")
                break
