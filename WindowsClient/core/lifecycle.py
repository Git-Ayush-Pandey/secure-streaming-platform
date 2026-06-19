import asyncio
import logging

logger = logging.getLogger("Lifecycle")

class Lifecycle:
    def __init__(self):
        self._shutdown_event = asyncio.Event()
        self._tasks = set()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    def request_shutdown(self):
        logger.info("Application shutdown sequence initiated.")
        self._shutdown_event.set()

    async def wait_for_shutdown(self):
        await self._shutdown_event.wait()

    def track_task(self, task: asyncio.Task):
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self):
        self.request_shutdown()
        
        # Cancel all tracked background tasks
        if self._tasks:
            logger.info(f"Cancelling {len(self._tasks)} tracked background tasks")
            for task in list(self._tasks):
                task.cancel()
            
            # Await cancellations
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        
        logger.info("Lifecycle shutdown complete.")
