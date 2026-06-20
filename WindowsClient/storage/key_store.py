import base64
import os
import stat
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
PASSPHRASE_FILE = KEY_DIR / ".key_passphrase"


def _load_or_create_passphrase() -> bytes:
    """
    F4: load or generate a random 32-byte passphrase used to encrypt the
    client's Ed25519 private key at rest. Mirrors the server-side pattern
    in server/backend/services/crypto_service.py (_load_or_create_passphrase),
    so a stolen client_private.pem alone is not enough to impersonate this
    device — the passphrase file would also have to be exfiltrated.

    Future: replace with Windows DPAPI (CryptProtectData) for stronger,
    user-profile-bound protection instead of a sibling secret file.
    """
    if PASSPHRASE_FILE.exists():
        return PASSPHRASE_FILE.read_bytes()

    passphrase = os.urandom(32)
    PASSPHRASE_FILE.write_bytes(passphrase)
    try:
        os.chmod(PASSPHRASE_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass  # Windows may not support POSIX chmod — acceptable fallback

    return passphrase


def _save_encrypted_private_key(priv: Ed25519PrivateKey, passphrase: bytes) -> None:
    PRIVATE_KEY.write_bytes(
        priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(passphrase),
        )
    )
    try:
        os.chmod(PRIVATE_KEY, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def _load_private_key_with_migration(passphrase: bytes) -> Ed25519PrivateKey:
    """
    Try loading the private key with the passphrase. If that fails because
    an existing key was written unencrypted by a previous client version,
    load it without a password and immediately re-save it encrypted
    (one-time migration, same approach as the backend).
    """
    raw = PRIVATE_KEY.read_bytes()
    try:
        return serialization.load_pem_private_key(raw, password=passphrase)
    except (ValueError, TypeError):
        pass

    private_key = serialization.load_pem_private_key(raw, password=None)
    _save_encrypted_private_key(private_key, passphrase)
    return private_key


def load_or_create_keys():

    passphrase = _load_or_create_passphrase()

    if PRIVATE_KEY.exists() and PUBLIC_KEY.exists():

        priv = _load_private_key_with_migration(passphrase)

        with open(PUBLIC_KEY, "rb") as f:
            pub = serialization.load_pem_public_key(
                f.read()
            )

        return priv, pub

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    _save_encrypted_private_key(priv, passphrase)

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