import struct
import logging
import time
from typing import Optional, Tuple
from .crypto_service import aes_decrypt

logger = logging.getLogger("FrameReassembler")

class FrameReassembler:
    def __init__(self):
        # frame_seq -> {
        #    "fragments": {frag_index: chunk_bytes},
        #    "frag_count": int,
        #    "codec_tag": int,
        #    "flags": int,
        #    "nonce": bytes,
        #    "timestamp": float
        # }
        self.buffers = {}
        self.last_successful_seq = -1

    def process_packet(self, packet: bytes, session_key: bytes) -> Optional[Tuple[bytes, int, bool]]:
        """
        Process a single UDP packet. If it completes a frame, decrypts and returns:
        (decrypted_frame_bytes, codec_tag, is_keyframe)
        Otherwise returns None.
        """
        if len(packet) < 18:
            logger.debug("Received packet too short for header")
            return None

        # Wire format:
        # [1B codec_tag][1B flags][8B frame_seq BE][2B frag_index BE][2B frag_count BE][4B nonce_len]
        try:
            codec_tag, flags, frame_seq, frag_index, frag_count, nonce_len = struct.unpack(
                ">BBQHHI", packet[:18]
            )
        except Exception as e:
            logger.error(f"Failed to unpack header: {e}")
            return None

        # Discard stale frames (already passed the seq)
        if frame_seq <= self.last_successful_seq:
            return None

        if 18 + nonce_len > len(packet):
            logger.error("Packet shorter than header + nonce_len")
            return None

        nonce = packet[18 : 18 + nonce_len]
        chunk = packet[18 + nonce_len :]

        # Initialize buffer for this frame
        if frame_seq not in self.buffers:
            # Run cleanup occasionally to avoid memory build up from dropped frames
            self._cleanup_stale_buffers()
            
            self.buffers[frame_seq] = {
                "fragments": {},
                "frag_count": frag_count,
                "codec_tag": codec_tag,
                "flags": flags,
                "nonce": nonce,
                "timestamp": time.time()
            }

        buf = self.buffers[frame_seq]
        buf["fragments"][frag_index] = chunk

        # Check if complete
        if len(buf["fragments"]) == buf["frag_count"]:
            # Reassemble
            try:
                ciphertext = b"".join(buf["fragments"][i] for i in range(buf["frag_count"]))
                
                # Decrypt
                aad = struct.pack(">Q", frame_seq)
                decrypted = aes_decrypt(session_key, buf["nonce"], ciphertext, aad=aad)
                
                # Update seq
                self.last_successful_seq = frame_seq
                
                # Clean up all frames <= frame_seq
                stale_keys = [k for k in self.buffers.keys() if k <= frame_seq]
                for k in stale_keys:
                    self.buffers.pop(k, None)
                    
                is_keyframe = (buf["flags"] & 0x01) != 0
                return decrypted, buf["codec_tag"], is_keyframe
                
            except Exception as e:
                logger.error(f"Failed to decrypt frame {frame_seq}: {e}")
                # Remove this frame buffer so we don't try again
                self.buffers.pop(frame_seq, None)
                return None

        return None

    def _cleanup_stale_buffers(self):
        """Discard partially received frames that have stalled for over 1.5 seconds."""
        now = time.time()
        stale_keys = [
            k for k, v in self.buffers.items()
            if now - v["timestamp"] > 1.5
        ]
        for k in stale_keys:
            v = self.buffers[k]
            received = len(v["fragments"])
            total = v["frag_count"]
            # DIAGNOSTIC (video pipeline audit): this is the direct, in-band
            # evidence of incomplete-frame loss. If this fires continuously
            # with received << total, the frame size / fragment count is too
            # high for the network path to deliver before frames go stale.
            logger.warning(
                f"Discarded incomplete frame {k}: received {received}/{total} "
                f"fragments ({received/total:.0%}) before 1.5s timeout"
            )
            self.buffers.pop(k, None)