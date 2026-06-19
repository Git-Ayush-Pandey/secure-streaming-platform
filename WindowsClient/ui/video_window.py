import asyncio
import logging
import cv2
import numpy as np
from .status_panel import StatusPanel
from core.connection_manager import ConnectionManager
from core.state_machine import StateMachine

logger = logging.getLogger("VideoWindow")

class VideoWindow:
    def __init__(self, manager: ConnectionManager, width: int = 1280, height: int = 720):
        self.manager = manager
        self.width = width
        self.height = height
        self.status_panel = StatusPanel()
        
        self._latest_frame = None
        self._state = StateMachine.DISCONNECTED
        self._details = None
        
        # Subscribe to callbacks and events from the orchestrator
        self.manager.set_frame_callback(self._on_frame_received)
        self.manager.state_machine.add_listener(self._on_state_changed)

    def _on_frame_received(self, frame: np.ndarray, is_keyframe: bool):
        self._latest_frame = frame
        self.status_panel.update_fps()

    def _on_state_changed(self, event):
        self._state = event.new_state
        self._details = event.details
        if self._state != StateMachine.CONNECTED:
            # Clear stale frame when disconnecting
            self._latest_frame = None

    async def run_loop(self):
        """Video window render loop. Must run on the main execution thread."""
        logger.info("Initializing OpenCV rendering window...")

        WINDOW_NAME = "Secure Streaming"

        cv2.namedWindow(
            WINDOW_NAME,
            cv2.WINDOW_NORMAL
        )

        cv2.resizeWindow(
            WINDOW_NAME,
            self.width,
            self.height
        )

        fullscreen = False

        try:

            while not self.manager.lifecycle.is_shutting_down:

                state = self.manager.state_machine.state

                if (
                    state == StateMachine.CONNECTED
                    and self._latest_frame is not None
                ):

                    frame_copy = self._latest_frame.copy()

                    frame_with_overlay = (
                        self.status_panel.draw_overlay(
                            frame_copy,
                            state,
                            self._details
                        )
                    )

                    cv2.imshow(
                        WINDOW_NAME,
                        frame_with_overlay
                    )

                else:

                    splash = (
                        self.status_panel.draw_splash_screen(
                            self.width,
                            self.height,
                            state,
                            self._details
                        )
                    )

                    cv2.imshow(
                        WINDOW_NAME,
                        splash
                    )

                await asyncio.sleep(0.03)

                key = cv2.waitKey(1) & 0xFF

                if key in (
                    ord('q'),
                    ord('Q')
                ):

                    logger.info(
                        "User requested exit."
                    )

                    self.manager.lifecycle.request_shutdown()
                    break

                if key in (
                    ord('f'),
                    ord('F')
                ):

                    fullscreen = not fullscreen

                    cv2.setWindowProperty(
                        WINDOW_NAME,
                        cv2.WND_PROP_FULLSCREEN,
                        cv2.WINDOW_FULLSCREEN
                        if fullscreen
                        else cv2.WINDOW_NORMAL
                    )

                    if not fullscreen:
                        cv2.resizeWindow(
                            WINDOW_NAME,
                            self.width,
                            self.height
                        )

        except Exception as e:

            logger.error(
                f"Render window exception encountered: {e}"
            )

        finally:

            logger.info(
                "Closing all active video window contexts."
            )

            try:
                cv2.destroyWindow(WINDOW_NAME)
            except:
                pass

            cv2.destroyAllWindows()