import asyncio
import sys
import logging
from config.logging_config import setup_logging
from core.connection_manager import ConnectionManager
from ui.video_window import VideoWindow

logger = logging.getLogger("ClientMain")

async def main():
    setup_logging()
    logger.info("Starting Secure Drone Stream Client...")
    
    manager = ConnectionManager()
    await manager.start()
    
    window = VideoWindow(manager)
    
    try:
        # Run OpenCV render loop on the main thread
        await window.run_loop()
    except KeyboardInterrupt:
        logger.info("Application interrupted via keyboard (Ctrl+C).")
    finally:
        logger.info("Initiating client cleanup...")
        await manager.stop()
        logger.info("Client shutdown completed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal client error: {e}", file=sys.stderr)
        sys.exit(1)