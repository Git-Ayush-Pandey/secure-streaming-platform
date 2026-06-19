import unittest
import os
import sys
from pathlib import Path

# Add parent directory to path to resolve local client imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from services.crypto_service import (
    generate_x25519_keypair, x25519_exchange, derive_session_key,
    aes_decrypt, verify_server_signature
)

class TestCryptoService(unittest.TestCase):
    def test_x25519_keypair_generation(self):
        priv, pub = generate_x25519_keypair()
        self.assertIsNotNone(priv)
        self.assertIsNotNone(pub)

    def test_ecdh_exchange_and_derivation(self):
        # Client keys
        c_priv, c_pub = generate_x25519_keypair()
        c_pub_bytes = c_pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        
        # Server keys
        s_priv, s_pub = generate_x25519_keypair()
        s_pub_bytes = s_pub.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        
        # Exchange
        c_shared = x25519_exchange(c_priv, s_pub_bytes)
        s_shared = x25519_exchange(s_priv, c_pub_bytes)
        
        # Shared secret must match
        self.assertEqual(c_shared, s_shared)
        
        # Derivation
        salt = os.urandom(32)
        c_key = derive_session_key(c_shared, salt)
        s_key = derive_session_key(s_shared, salt)
        
        self.assertEqual(c_key, s_key)
        self.assertEqual(len(c_key), 32)

    def test_aes_gcm_decryption(self):
        key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        plaintext = b"top-secret-drone-coordinates"
        aad = b"frame-seq-42"
        
        # Encrypt
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
        
        # Decrypt using helper
        decrypted = aes_decrypt(key, nonce, ciphertext, aad)
        self.assertEqual(decrypted, plaintext)

    def test_server_signature_verification(self):
        priv_signing = Ed25519PrivateKey.generate()
        pub_signing = priv_signing.public_key()
        pub_bytes = pub_signing.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw
        )
        
        msg = b"challenge-binding-details"
        sig = priv_signing.sign(msg)
        
        # Verify
        self.assertTrue(verify_server_signature(pub_bytes, msg, sig))
        
        # Verify failure on corrupt msg
        self.assertFalse(verify_server_signature(pub_bytes, msg + b"corrupt", sig))

if __name__ == "__main__":
    unittest.main()
