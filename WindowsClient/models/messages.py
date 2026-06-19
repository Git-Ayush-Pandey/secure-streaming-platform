from dataclasses import dataclass

@dataclass
class HelloMessage:
    device_id: str
    device_name: str
    public_key_b64: str
    x25519_public_b64: str

@dataclass
class ChallengeResponseMessage:
    fingerprint: str
    signature_b64: str
