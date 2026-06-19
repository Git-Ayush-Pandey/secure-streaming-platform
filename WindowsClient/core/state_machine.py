import logging
from typing import Callable, List
from models.events import StateChangeEvent

logger = logging.getLogger("StateMachine")

class StateMachine:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    CONNECTED = "CONNECTED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"

    def __init__(self, initial_state: str = DISCONNECTED):
        self._state = initial_state
        self._listeners: List[Callable[[StateChangeEvent], None]] = []

    @property
    def state(self) -> str:
        return self._state

    def add_listener(self, listener: Callable[[StateChangeEvent], None]):
        self._listeners.append(listener)

    def transition_to(self, new_state: str, details: str = None) -> None:
        if self._state == new_state:
            return
        
        old_state = self._state
        self._state = new_state
        logger.info(f"State transition: {old_state} -> {new_state} ({details or ''})")
        
        event = StateChangeEvent(old_state=old_state, new_state=new_state, details=details)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error in state change listener: {e}")
