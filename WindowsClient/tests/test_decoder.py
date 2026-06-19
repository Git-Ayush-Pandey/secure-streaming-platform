import unittest
import sys
from pathlib import Path
import numpy as np
import cv2

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.decoder import VideoDecoder

class TestDecoderService(unittest.TestCase):
    def setUp(self):
        self.decoder = VideoDecoder()
        
    def test_jpeg_decoding(self):
        # Generate a dummy solid green frame using numpy
        img = np.zeros((120, 120, 3), dtype=np.uint8)
        img[:, :] = (0, 255, 0)  # BGR green
        
        # Compress it as JPEG bytes
        ok, buf = cv2.imencode(".jpg", img)
        self.assertTrue(ok)
        jpeg_bytes = buf.tobytes()
        
        # Decode via VideoDecoder
        decoded = self.decoder.decode(jpeg_bytes, codec_tag=0x01)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, (120, 120, 3))
        # Assert pixels match BGR green within small margin of error (JPEG is lossy)
        diff = np.abs(decoded[5, 5].astype(int) - np.array([0, 255, 0]))
        self.assertTrue(np.all(diff < 5))

    def test_h264_decoding_graceful_failure_on_corrupt(self):
        # Passing invalid binary streams should not crash the process; it returns None
        res = self.decoder.decode(b"corrupt-data-stream-404", codec_tag=0x02)
        self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()
