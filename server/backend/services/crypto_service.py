"""
Cryptographic primitives — Hardened Edition.

Changes vs previous version:
  ✓ Server private key encrypted at rest (passphrase stored in .key_passphrase)
  ✓ Migration: auto-re-encrypts unprotected existing keys on first load
  ✓ HMAC-SHA256 helpers for UDP heartbeat authentication
  ✓ X25519 + HKDF-SHA256 session key derivation
  ✓ AES-256-GCM frame encryption with optional AAD
"""
from __future__ import annotations
import base64
import hashlib
import hmac as _hmac
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey,
)
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ── Passphrase-protected key storage ────────────────────────────────────────

def _load_or_create_passphrase(keys_dir: Path) -> bytes:
    """
    Load or generate a random 32-byte passphrase used to encrypt the server
    private key at rest.  The passphrase file itself has restricted permissions.

    Future: replace with Windows DPAPI or HSM for stronger protection.
    """
    pass_file = keys_dir / ".key_passphrase"
    if pass_file.exists():
        return pass_file.read_bytes()

    passphrase = os.urandom(32)
    pass_file.write_bytes(passphrase)

    # Restrict to owner read/write only (best-effort on Windows)
    try:
        os.chmod(pass_file, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass  # Windows may not support POSIX chmod — acceptable fallback

    return passphrase


# ── Ed25519 identity keys ────────────────────────────────────────────────────

def ensure_server_keys(
    keys_dir: Path,
) -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """
    Load or generate persistent Ed25519 server identity keys.
    Private key is encrypted at rest using a machine-local passphrase.
    Automatically migrates unencrypted keys to encrypted format.
    """
    priv_path  = keys_dir / "server_private.pem"
    pub_path   = keys_dir / "server_public.pem"
    passphrase = _load_or_create_passphrase(keys_dir)

    if priv_path.exists() and pub_path.exists():
        private_key = _load_private_key_with_migration(priv_path, passphrase)
        with open(pub_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())
        return private_key, public_key

    # Generate new keys
    private_key = Ed25519PrivateKey.generate()
    public_key  = private_key.public_key()

    _save_encrypted_private_key(private_key, priv_path, passphrase)
    with open(pub_path, "wb") as f:
        f.write(public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
    return private_key, public_key


def _load_private_key_with_migration(
    priv_path: Path, passphrase: bytes
) -> Ed25519PrivateKey:
    """
    Try loading the private key with the passphrase.
    If that fails (unencrypted legacy key), load it unencrypted and
    immediately re-save it encrypted (one-time migration).
    """
    raw = priv_path.read_bytes()
    try:
        return serialization.load_pem_private_key(raw, password=passphrase)
    except (ValueError, TypeError):
        pass

    # Legacy: try loading without password (unencrypted key)
    try:
        private_key = serialization.load_pem_private_key(raw, password=None)
        # Migrate: re-save with encryption
        _save_encrypted_private_key(private_key, priv_path, passphrase)
        return private_key
    except Exception as exc:
        raise RuntimeError(
            f"Cannot load server private key from {priv_path}: {exc}"
        ) from exc


def _save_encrypted_private_key(
    private_key: Ed25519PrivateKey, path: Path, passphrase: bytes
) -> None:
    path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(passphrase),
        )
    )
    # Restrict permissions
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def get_server_public_b64(keys_dir: Path) -> str:
    """Return raw (not PEM) base64-encoded Ed25519 public key."""
    pub_path = keys_dir / "server_public.pem"
    with open(pub_path, "rb") as f:
        pub = serialization.load_pem_public_key(f.read())
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def fingerprint(public_key: Ed25519PublicKey) -> str:
    raw    = public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    digest = hashlib.sha256(raw).hexdigest()
    return ":".join(digest[i:i+4] for i in range(0, 32, 4))


def fingerprint_from_raw_b64(raw_b64: str) -> str:
    raw    = base64.b64decode(raw_b64)
    digest = hashlib.sha256(raw).hexdigest()
    return ":".join(digest[i:i+4] for i in range(0, 32, 4))


def public_key_from_raw(raw: bytes) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(raw)


def verify(
    public_key: Ed25519PublicKey, message: bytes, signature: bytes
) -> bool:
    try:
        public_key.verify(signature, message)
        return True
    except Exception:
        return False


def generate_challenge() -> bytes:
    return os.urandom(32)


# ── HMAC-SHA256 helpers (UDP heartbeat authentication) ───────────────────────

def hmac_sign(key: bytes, message: bytes) -> bytes:
    """Produce a 32-byte HMAC-SHA256 tag over message using key."""
    return _hmac.new(key, message, hashlib.sha256).digest()


def hmac_verify(key: bytes, message: bytes, tag: bytes) -> bool:
    """Constant-time HMAC-SHA256 verification."""
    expected = _hmac.new(key, message, hashlib.sha256).digest()
    return _hmac.compare_digest(expected, tag)


# ── X25519 ephemeral key exchange ────────────────────────────────────────────

def generate_x25519_keypair() -> tuple[X25519PrivateKey, X25519PublicKey]:
    """Generate a fresh ephemeral X25519 keypair for one ECDH exchange."""
    priv = X25519PrivateKey.generate()
    return priv, priv.public_key()


def x25519_exchange(
    private_key: X25519PrivateKey, peer_pub_bytes: bytes
) -> bytes:
    """Perform X25519 DH and return the raw 32-byte shared secret."""
    peer_pub = X25519PublicKey.from_public_bytes(peer_pub_bytes)
    return private_key.exchange(peer_pub)


def derive_session_key(shared_secret: bytes, salt: bytes) -> bytes:
    """
    Derive a 32-byte AES session key from an X25519 shared secret via
    HKDF-SHA256.  Salt = challenge bytes → unique key per session.
    The key is NEVER sent over the wire.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"drone-stream-v1-aes-session",
    )
    return hkdf.derive(shared_secret)


# ── AES-256-GCM frame encryption ─────────────────────────────────────────────

def aes_encrypt(
    key: bytes, plaintext: bytes, aad: bytes | None = None
) -> tuple[bytes, bytes]:
    """
    Encrypt with AES-256-GCM.
    Returns (nonce, ciphertext_with_16B_GCM_tag).
    Optional aad is authenticated but not encrypted.
    """
    nonce  = os.urandom(12)
    aesgcm = AESGCM(key)
    ct     = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce, ct


def aes_decrypt(
    key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes | None = None
) -> bytes:
    """Decrypt AES-256-GCM.  Raises on tag mismatch."""
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, aad)