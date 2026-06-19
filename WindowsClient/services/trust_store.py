import json
import logging
from config.settings import TRUSTED_SERVERS_DIR

logger = logging.getLogger("TrustStore")
TRUST_FILE = TRUSTED_SERVERS_DIR / "trusted_server.json"

def load_trusted_fingerprint() -> str | None:
    if TRUST_FILE.exists():
        try:
            with open(TRUST_FILE, "r") as f:
                data = json.load(f)
                return data.get("fingerprint")
        except Exception as exc:
            logger.error("Failed to read trust store: %s", exc)
    return None

def save_trusted_fingerprint(fingerprint: str) -> None:
    try:
        with open(TRUST_FILE, "w") as f:
            json.dump({"fingerprint": fingerprint}, f)
        logger.info("Saved server fingerprint to trust store: %s", fingerprint)
    except Exception as exc:
        logger.error("Failed to save trust store: %s", exc)

def verify_or_save_server(fingerprint: str) -> bool:
    trusted = load_trusted_fingerprint()
    if trusted is None:
        logger.info("TOFU: First-time server connection. Trusting fingerprint: %s", fingerprint)
        save_trusted_fingerprint(fingerprint)
        return True
    
    if trusted != fingerprint:
        logger.error(
            "POSSIBLE MITM ATTACK DETECTED!\n"
            "The server fingerprint has changed!\n"
            "Expected: %s\n"
            "Received: %s",
            trusted, fingerprint
        )
        return False
    return True
