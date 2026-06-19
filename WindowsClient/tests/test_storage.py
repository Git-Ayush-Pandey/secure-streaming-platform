import unittest
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import storage.key_store as key_store
import storage.config_store as config_store
import storage.local_db as local_db

class TestStorageServices(unittest.TestCase):
    def setUp(self):
        # Redirect file paths to a temporary directory to avoid disturbing active keys
        self.test_dir = Path(tempfile.mkdtemp())
        
        self.original_key_dir = key_store.KEY_DIR
        self.original_private_key = key_store.PRIVATE_KEY
        self.original_public_key = key_store.PUBLIC_KEY
        
        key_store.KEY_DIR = self.test_dir / "keys"
        key_store.KEY_DIR.mkdir(parents=True, exist_ok=True)
        key_store.PRIVATE_KEY = key_store.KEY_DIR / "client_private.pem"
        key_store.PUBLIC_KEY = key_store.KEY_DIR / "client_public.pem"
        
        self.original_config_file = config_store.CONFIG_FILE
        config_store.CONFIG_FILE = self.test_dir / "client_config.json"
        
        self.original_session_file = local_db.SESSION_CACHE_FILE
        local_db.SESSION_CACHE_FILE = self.test_dir / "session_cache.json"

    def tearDown(self):
        # Restore configuration paths
        key_store.KEY_DIR = self.original_key_dir
        key_store.PRIVATE_KEY = self.original_private_key
        key_store.PUBLIC_KEY = self.original_public_key
        
        config_store.CONFIG_FILE = self.original_config_file
        local_db.SESSION_CACHE_FILE = self.original_session_file
        
        # Wipe temp directory
        shutil.rmtree(self.test_dir)

    def test_key_store_load_or_create(self):
        # First check: creates a new key pair
        priv1, pub1 = key_store.load_or_create_keys()
        self.assertIsNotNone(priv1)
        self.assertIsNotNone(pub1)
        self.assertTrue(key_store.PRIVATE_KEY.exists())
        self.assertTrue(key_store.PUBLIC_KEY.exists())
        
        # Second check: loads identical keys from disk
        priv2, pub2 = key_store.load_or_create_keys()
        
        from cryptography.hazmat.primitives import serialization
        pub1_bytes = pub1.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        pub2_bytes = pub2.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.assertEqual(pub1_bytes, pub2_bytes)

    def test_config_store_load_save(self):
        # Load from clean slate -> empty dict
        config = config_store.load_client_config()
        self.assertEqual(config, {})
        
        # Save configuration properties
        test_cfg = {"device_id": "test-device", "name": "Test Name"}
        config_store.save_client_config(test_cfg)
        
        # Load back and verify
        loaded = config_store.load_client_config()
        self.assertEqual(loaded, test_cfg)

    def test_local_db_session_cache(self):
        # Load clean session cache -> None
        self.assertIsNone(local_db.get_cached_session())
        
        # Save session parameters
        session_data = {"session_key_hex": "abcd", "port": 8765}
        local_db.save_session_cache(session_data)
        
        # Verify loading works
        loaded = local_db.get_cached_session()
        self.assertEqual(loaded, session_data)
        
        # Clear cache and check removal
        local_db.clear_session_cache()
        self.assertIsNone(local_db.get_cached_session())

if __name__ == "__main__":
    unittest.main()
