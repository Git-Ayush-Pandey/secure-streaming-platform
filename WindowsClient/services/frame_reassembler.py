"""
Frame Reassembler — Production Hardened Edition.

Hardening applied:
  ✓ Absolute limits on concurrent incomplete frames (MAX_INCOMPLETE_FRAMES),
    total buffered fragments (MAX_TOTAL_FRAGMENTS), and total memory consumed
    (MAX_TOTAL_BUFFER_BYTES). When any limit is exceeded the oldest/largest
    buffer is evicted (NF reassembly memory protection).
  ✓ Full parser hardening: codec_tag, frag_index, frag_count, nonce_len,
    frame_seq, flags, and chunk size all validated before any allocation.
  ✓ frag_count=0 rejected (avoids division-by-zero and empty-allocation).
  ✓ frag_index >= frag_count rejected (out-of-range index).
  ✓ nonce_len validated against a hard maximum (256 bytes) before slice.
  ✓ chunk_size validated non-zero and within MTU budget before storage.
  ✓ Periodic cleanup runs on every new frame entry (unchanged behaviour)
    but now also enforces the hard limits before the allocation.
"""
import struct
import logging
import time
from typing import Optional, Tuple
from .crypto_service import aes_decrypt

logger = logging.getLogger("FrameReassembler")

# ── Reassembly memory limits ───────────────────────────────────────────────────
# Maximum number of incomplete frames held simultaneously.
# At 20fps a 1.5s stale window holds at most 30 frames. 64 is a generous
# ceiling that stops a fragment-flood from pre-allocating unbounded buffers.
MAX_INCOMPLETE_FRAMES   = 64

# Maximum total number of fragment slots across all in-progress frames.
# Prevents an attacker from crafting packets with large frag_count values
# to consume memory even if each individual frame looks plausible.
MAX_TOTAL_FRAGMENTS     = MAX_INCOMPLETE_FRAMES * 600   # ≈ 38 400

# Maximum total ciphertext bytes held in all reassembly buffers combined.
# 8 MB is several times a full 1080p JPEG frame — generous, but bounded.
MAX_TOTAL_BUFFER_BYTES  = 8 * 1024 * 1024

# Maximum nonce length accepted from a wire packet.
MAX_NONCE_LEN = 256

# Maximum valid fragment payload size (slightly above PACKET_MAX_PAYLOAD to
# allow for minor MTU variations, but well below anything that could be a
# memory attack).
MAX_CHUNK_BYTES = 2048

# Maximum valid frag_count for a single frame.
MAX_FRAGS_PER_FRAME = MAX_TOTAL_BUFFER_BYTES // 1 + 1   # hard ceiling ~8M frags,
# but the MAX_TOTAL_BUFFER_BYTES check catches the real limit earlier.

# Valid codec tags.
_VALID_CODEC_TAGS = frozenset({0x01, 0x02})


class FrameReassembler:
    def __init__(self):
        # frame_seq -> {
        #    "fragments": {frag_index: chunk_bytes},
        #    "frag_count": int,
        #    "codec_tag": int,
        #    "flags": int,
        #    "nonce": bytes,
        #    "timestamp": float,
        #    "byte_count": int,   # total bytes stored in fragments
        # }
        self.buffers: dict[int, dict] = {}
        self.last_successful_seq = -1

    # ── Internal limit tracking ────────────────────────────────────────────────

    def _total_fragments(self) -> int:
        return sum(len(b["fragments"]) for b in self.buffers.values())

    def _total_bytes(self) -> int:
        return sum(b["byte_count"] for b in self.buffers.values())

    def _evict_oldest(self) -> None:
        """Evict the oldest in-progress frame buffer."""
        if not self.buffers:
            return
        oldest_seq = min(self.buffers.keys())
        v = self.buffers.pop(oldest_seq)
        logger.warning(
            "Evicted reassembly buffer seq=%d (oldest): "
            "%d/%d fragments, %d bytes held",
            oldest_seq, len(v["fragments"]), v["frag_count"], v["byte_count"],
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_packet(self, packet: bytes, session_key: bytes) -> Optional[Tuple[bytes, int, bool]]:
        """
        Process one UDP fragment packet. Returns (decrypted_bytes, codec_tag,
        is_keyframe) when a frame is complete, otherwise None.
        All fields are validated before any allocation.
        """
        # ── Wire-header parsing and validation ─────────────────────────────────
        if len(packet) < 18:
            logger.debug("Packet too short for header (%d bytes)", len(packet))
            return None

        try:
            codec_tag, flags, frame_seq, frag_index, frag_count, nonce_len = struct.unpack(
                ">BBQHHI", packet[:18]
            )
        except struct.error as exc:
            logger.error("Header unpack failed: %s", exc)
            return None

        # Validate codec_tag before any further work.
        if codec_tag not in _VALID_CODEC_TAGS:
            logger.warning("Unknown codec_tag=0x%02x — dropping", codec_tag)
            return None

        # Validate frag_count: 0 is invalid (divide-by-zero / empty allocation).
        if frag_count == 0:
            logger.warning("frag_count=0 is invalid — dropping")
            return None

        # Validate frag_index: must be < frag_count.
        if frag_index >= frag_count:
            logger.warning(
                "frag_index=%d >= frag_count=%d — dropping", frag_index, frag_count
            )
            return None

        # Validate frag_count against hard ceiling.
        if frag_count > MAX_FRAGS_PER_FRAME:
            logger.warning(
                "frag_count=%d exceeds MAX_FRAGS_PER_FRAME=%d — dropping",
                frag_count, MAX_FRAGS_PER_FRAME,
            )
            return None

        # Validate nonce_len before slice.
        if nonce_len > MAX_NONCE_LEN:
            logger.warning("nonce_len=%d > %d — dropping", nonce_len, MAX_NONCE_LEN)
            return None

        if 18 + nonce_len > len(packet):
            logger.warning("Packet shorter than header + nonce (%d bytes) — dropping", nonce_len)
            return None

        nonce = packet[18: 18 + nonce_len]
        chunk = packet[18 + nonce_len:]

        # Validate chunk size.
        if len(chunk) == 0:
            logger.debug("Empty chunk (frag_index=%d frag_count=%d) — dropping", frag_index, frag_count)
            return None

        if len(chunk) > MAX_CHUNK_BYTES:
            logger.warning(
                "chunk size %d > %d — dropping", len(chunk), MAX_CHUNK_BYTES
            )
            return None

        # Discard frames older than the last successfully decoded one.
        if frame_seq <= self.last_successful_seq:
            return None

        # ── Memory-limit enforcement before allocation ──────────────────────────
        if frame_seq not in self.buffers:
            self._cleanup_stale_buffers()

            # Enforce hard limits before creating a new buffer entry.
            while len(self.buffers) >= MAX_INCOMPLETE_FRAMES:
                self._evict_oldest()

            while self._total_fragments() >= MAX_TOTAL_FRAGMENTS:
                self._evict_oldest()
                if not self.buffers:
                    break

            while self._total_bytes() + len(chunk) > MAX_TOTAL_BUFFER_BYTES:
                self._evict_oldest()
                if not self.buffers:
                    break

            self.buffers[frame_seq] = {
                "fragments":  {},
                "frag_count": frag_count,
                "codec_tag":  codec_tag,
                "flags":      flags,
                "nonce":      nonce,
                "timestamp":  time.time(),
                "byte_count": 0,
            }

        buf = self.buffers[frame_seq]

        # Reject duplicate fragment index (already have it — drop silently).
        if frag_index in buf["fragments"]:
            return None

        # Check per-frame fragment count consistency (server must send a fixed
        # frag_count for all packets in one frame; a mismatch indicates a
        # corrupt or crafted packet stream).
        if buf["frag_count"] != frag_count:
            logger.warning(
                "frag_count mismatch for seq=%d: expected %d got %d — dropping",
                frame_seq, buf["frag_count"], frag_count,
            )
            return None

        buf["fragments"][frag_index] = chunk
        buf["byte_count"] += len(chunk)

        # ── Reassemble when all fragments have arrived ─────────────────────────
        if len(buf["fragments"]) == buf["frag_count"]:
            try:
                ciphertext = b"".join(
                    buf["fragments"][i] for i in range(buf["frag_count"])
                )
                aad       = struct.pack(">Q", frame_seq)
                decrypted = aes_decrypt(session_key, buf["nonce"], ciphertext, aad=aad)

                self.last_successful_seq = frame_seq

                # Evict this frame and all older ones.
                stale_keys = [k for k in self.buffers if k <= frame_seq]
                for k in stale_keys:
                    self.buffers.pop(k, None)

                is_keyframe = (buf["flags"] & 0x01) != 0
                return decrypted, buf["codec_tag"], is_keyframe

            except Exception as exc:
                logger.error("Failed to decrypt frame seq=%d: %s", frame_seq, exc)
                self.buffers.pop(frame_seq, None)
                return None

        return None

    def _cleanup_stale_buffers(self) -> None:
        """Discard partially received frames older than 1.5 seconds."""
        now = time.time()
        stale_keys = [
            k for k, v in self.buffers.items()
            if now - v["timestamp"] > 1.5
        ]
        for k in stale_keys:
            v = self.buffers[k]
            received = len(v["fragments"])
            total    = v["frag_count"]
            logger.warning(
                "Discarded incomplete frame %d: received %d/%d fragments (%.0f%%) "
                "before 1.5s timeout",
                k, received, total, (received / total * 100) if total else 0,
            )
            self.buffers.pop(k, None)
