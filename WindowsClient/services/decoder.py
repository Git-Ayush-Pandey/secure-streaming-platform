import logging
from typing import Optional
import numpy as np
import cv2

try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False

logger = logging.getLogger("Decoder")

class VideoDecoder:
    def __init__(self):
        self.av_ctx = None
        if AV_AVAILABLE:
            self._init_av()
        else:
            logger.warning("PyAV 'av' library is not installed. H264 streams cannot be decoded. Falling back to JPEG support only.")

    def _init_av(self):
        try:
            self.av_ctx = av.CodecContext.create('h264', 'r')
            logger.info("PyAV H264 decoder context initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PyAV H264 decoder: {e}")
            self.av_ctx = None

    def decode_h264(self, data: bytes) -> Optional[np.ndarray]:
        if not AV_AVAILABLE:
            logger.error("H264 packet received but PyAV is not installed.")
            return None
        if not self.av_ctx:
            self._init_av()
            if not self.av_ctx:
                return None
        try:
            packet = av.Packet(data)
            frames = self.av_ctx.decode(packet)
            if frames:
                # Convert PyAV VideoFrame to numpy BGR array (expected by OpenCV)
                return frames[0].to_ndarray(format='bgr24')
        except Exception as e:
            logger.error(f"Failed to decode H264 frame: {e}")
            # Re-initialize context to clear any corrupted state
            self._init_av()
        return None

    def decode_jpeg(self, data: bytes) -> Optional[np.ndarray]:
        try:
            np_arr = np.frombuffer(data, dtype=np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.error(f"Failed to decode JPEG frame: {e}")
            return None

    def decode(self, data: bytes, codec_tag: int) -> Optional[np.ndarray]:
        if codec_tag == 0x01:  # JPEG
            return self.decode_jpeg(data)
        elif codec_tag == 0x02:  # H264
            return self.decode_h264(data)
        else:
            logger.error(f"Unknown codec tag received: {codec_tag}")
            return None
