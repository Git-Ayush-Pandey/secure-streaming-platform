import random

class RetryPolicy:
    def __init__(self, base_delay: float = 1.0, max_delay: float = 30.0, backoff_factor: float = 2.0, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.attempts = 0

    def reset(self):
        self.attempts = 0

    def get_delay(self) -> float:
        """Calculate wait delay for next retry attempt."""
        delay = self.base_delay * (self.backoff_factor ** self.attempts)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            # Add ±25% random jitter
            delay = delay * (0.75 + random.random() * 0.5)
            
        self.attempts += 1
        return delay
