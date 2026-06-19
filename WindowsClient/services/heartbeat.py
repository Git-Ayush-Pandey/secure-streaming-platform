import time
import os
import struct
import hmac
import hashlib
import logging
import socket

logger = logging.getLogger("Heartbeat")

def create_heartbeat_packet(fingerprint: str, session_key: bytes) -> bytes:
    """
    UDP Heartbeat Wire Format:
      [2B fp_len][fp_bytes][8B unix_timestamp_ms][16B nonce][32B HMAC-SHA256]
      HMAC message = fp_bytes + timestamp_bytes + nonce
      HMAC key     = AES session key
    """
    fp_bytes = fingerprint.encode("utf-8")
    fp_len = len(fp_bytes)
    
    ts_ms = int(time.time() * 1000)
    ts_bytes = struct.pack(">Q", ts_ms)
    
    nonce = os.urandom(16)
    
    hmac_msg = fp_bytes + ts_bytes + nonce
    tag = hmac.new(session_key, hmac_msg, hashlib.sha256).digest()
    
    packet = struct.pack(">H", fp_len) + fp_bytes + ts_bytes + nonce + tag
    return packet

def send_heartbeat(sock: socket.socket, server_ip: str, server_port: int, 
                   fingerprint: str, session_key: bytes) -> None:
    try:
        packet = create_heartbeat_packet(fingerprint, session_key)
        sock.sendto(packet, (server_ip, server_port))
        logger.debug(f"Heartbeat sent to {server_ip}:{server_port}")
    except Exception as e:
        logger.error(f"Failed to send heartbeat: {e}")
