import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.state_machine import StateMachine

class TestStateMachine(unittest.TestCase):
    def test_state_transitions(self):
        machine = StateMachine(StateMachine.DISCONNECTED)
        self.assertEqual(machine.state, StateMachine.DISCONNECTED)
        
        events = []
        def listener(evt):
            events.append(evt)
            
        machine.add_listener(listener)
        
        # Transition DISCONNECTED -> CONNECTING
        machine.transition_to(StateMachine.CONNECTING, "WS connect initiated")
        self.assertEqual(machine.state, StateMachine.CONNECTING)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].old_state, StateMachine.DISCONNECTED)
        self.assertEqual(events[0].new_state, StateMachine.CONNECTING)
        self.assertEqual(events[0].details, "WS connect initiated")
        
        # Transition to identical state should be ignored (no redundant events)
        machine.transition_to(StateMachine.CONNECTING, "redundant transition attempt")
        self.assertEqual(len(events), 1)
        
        # Transition CONNECTING -> PENDING_APPROVAL
        machine.transition_to(StateMachine.PENDING_APPROVAL, "Waiting for operator")
        self.assertEqual(machine.state, StateMachine.PENDING_APPROVAL)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1].old_state, StateMachine.CONNECTING)
        self.assertEqual(events[1].new_state, StateMachine.PENDING_APPROVAL)

if __name__ == "__main__":
    unittest.main()
