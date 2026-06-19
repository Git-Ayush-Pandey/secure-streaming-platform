import time
import cv2
import numpy as np


class StatusPanel:

    def __init__(self):

        self.fps_timestamps = []
        self.fps_actual = 0.0

    def update_fps(self):

        now = time.time()

        self.fps_timestamps.append(now)

        self.fps_timestamps = [
            t for t in self.fps_timestamps
            if now - t <= 2.0
        ]

        if len(self.fps_timestamps) > 1:

            duration = (
                self.fps_timestamps[-1]
                - self.fps_timestamps[0]
            )

            self.fps_actual = (
                len(self.fps_timestamps)
                / (duration + 0.0001)
            )

    def draw_overlay(
        self,
        frame,
        state,
        details=None
    ):

        h, w = frame.shape[:2]

        overlay = frame.copy()

        cv2.rectangle(
            overlay,
            (0, 0),
            (w, 70),
            (20, 20, 20),
            -1
        )

        cv2.addWeighted(
            overlay,
            0.75,
            frame,
            0.25,
            0,
            frame
        )

        if state == "CONNECTED":
            color = (0, 255, 120)

        elif state in (
            "CONNECTING",
            "AUTHENTICATING",
            "PENDING_APPROVAL"
        ):
            color = (0, 180, 255)

        else:
            color = (0, 0, 255)

        cv2.putText(
            frame,
            f"SECURE STREAMING",
            (15, 28),
            cv2.FONT_HERSHEY_DUPLEX,
            0.7,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

        cv2.putText(
            frame,
            f"STATUS: {state}",
            (15, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            frame,
            f"FPS: {self.fps_actual:.1f}",
            (w - 160, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

        resolution = f"{w}x{h}"

        cv2.putText(
            frame,
            f"RES: {resolution}",
            (w - 160, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (200, 200, 200),
            1,
            cv2.LINE_AA
        )

        if details:

            cv2.putText(
                frame,
                details[:60],
                (250, 58),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (220, 220, 220),
                1,
                cv2.LINE_AA
            )

        return frame

    def draw_splash_screen(
        self,
        w,
        h,
        state,
        details=None
    ):

        img = np.zeros(
            (h, w, 3),
            dtype=np.uint8
        )

        img[:] = (18, 18, 18)

        cv2.putText(
            img,
            "SECURE STREAMING",
            (w // 2 - 180, h // 2 - 120),
            cv2.FONT_HERSHEY_DUPLEX,
            1.2,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        colors = {
            "CONNECTING": (0, 180, 255),
            "AUTHENTICATING": (0, 180, 255),
            "PENDING_APPROVAL": (0, 220, 255),
            "CONNECTED": (0, 255, 120),
            "BLOCKED": (0, 0, 255),
            "ERROR": (0, 0, 255),
            "DISCONNECTED": (160, 160, 160)
        }

        color = colors.get(
            state,
            (160, 160, 160)
        )

        cv2.putText(
            img,
            state,
            (w // 2 - 120, h // 2),
            cv2.FONT_HERSHEY_DUPLEX,
            1.0,
            color,
            2,
            cv2.LINE_AA
        )

        if details:

            cv2.putText(
                img,
                details[:70],
                (w // 2 - 250, h // 2 + 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                1,
                cv2.LINE_AA
            )

        cv2.putText(
            img,
            "Press F11 for fullscreen | Press Q to quit",
            (w // 2 - 180, h - 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (100, 100, 100),
            1,
            cv2.LINE_AA
        )

        return img