import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey
)

KEY_DIR = Path("data/keys")
KEY_DIR.mkdir(parents=True, exist_ok=True)

PRIVATE_KEY = KEY_DIR / "client_private.pem"
PUBLIC_KEY = KEY_DIR / "client_public.pem"


def load_or_create_keys():

    if PRIVATE_KEY.exists() and PUBLIC_KEY.exists():

        with open(PRIVATE_KEY, "rb") as f:
            priv = serialization.load_pem_private_key(
                f.read(),
                password=None
            )

        with open(PUBLIC_KEY, "rb") as f:
            pub = serialization.load_pem_public_key(
                f.read()
            )

        return priv, pub

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    PRIVATE_KEY.write_bytes(
        priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()
        )
    )

    PUBLIC_KEY.write_bytes(
        pub.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )

    return priv, pub


def public_key_b64(pub: Ed25519PublicKey):

    raw = pub.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw
    )

    return base64.b64encode(raw).decode()