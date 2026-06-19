from dataclasses import dataclass
from typing import Optional

@dataclass
class StateChangeEvent:
    old_state: str
    new_state: str
    details: Optional[str] = None

@dataclass
class FrameEvent:
    frame_bytes: bytes
    codec_tag: int
    is_keyframe: bool
