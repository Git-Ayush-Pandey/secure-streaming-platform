from dataclasses import dataclass
import time

@dataclass
class SessionInfo:
    session_key: bytes
    udp_port: int
    server_ip: str
    server_fingerprint: str
    created_at: float
    ttl: float = 1800.0

    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.ttl)
