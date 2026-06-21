import unittest
import sys
import os
import struct
import time
from pathlib import Path

# Add parent directory to path to resolve local client imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.heartbeat import create_heartbeat_packet

class TestClockSync(unittest.TestCase):
    def test_heartbeat_packet_with_offset(self):
        fingerprint = "4ccd:1026:7323:631f:a836:6fba:dc33:5819"
        session_key = b"A" * 32
        
        # Test 1: Heartbeat without offset
        packet_no_offset = create_heartbeat_packet(fingerprint, session_key, clock_offset_ms=0)
        
        # Unpack timestamp
        # Packet format: [2B fp_len][fp_bytes][8B unix_timestamp_ms][16B nonce][32B HMAC]
        fp_len = struct.unpack(">H", packet_no_offset[:2])[0]
        offset = 2 + fp_len
        ts_no_offset = struct.unpack(">Q", packet_no_offset[offset : offset + 8])[0]
        
        now_ms = int(time.time() * 1000)
        self.assertLess(abs(ts_no_offset - now_ms), 500)  # Should be within 500ms of current time
        
        # Test 2: Heartbeat with 44.5 seconds offset (44500 ms)
        offset_ms = 44500
        packet_with_offset = create_heartbeat_packet(fingerprint, session_key, clock_offset_ms=offset_ms)
        ts_with_offset = struct.unpack(">Q", packet_with_offset[offset : offset + 8])[0]
        
        # The timestamp with offset should be approximately ts_no_offset + offset_ms
        self.assertLess(abs(ts_with_offset - (ts_no_offset + offset_ms)), 100)
        
        # The difference between the offset-transposed timestamp and actual current time should be roughly offset_ms
        self.assertLess(abs((ts_with_offset - now_ms) - offset_ms), 500)

if __name__ == "__main__":
    unittest.main()
