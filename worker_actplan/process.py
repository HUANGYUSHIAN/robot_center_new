from __future__ import annotations

import base64

import cv2
import numpy as np

from tmui_tk_preview import TkImagePreviewThread


def decode_b64_jpeg(image_b64: str) -> np.ndarray | None:
    if not image_b64:
        return None
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        return None
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _placeholder_bgr(label: str) -> np.ndarray:
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.putText(img, label, (24, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 2)
    return img


def _hstack_left_right(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    h = min(left.shape[0], right.shape[0])
    if left.shape[0] != h:
        left = cv2.resize(left, (int(left.shape[1] * h / left.shape[0]), h), interpolation=cv2.INTER_AREA)
    if right.shape[0] != h:
        right = cv2.resize(right, (int(right.shape[1] * h / right.shape[0]), h), interpolation=cv2.INTER_AREA)
    return np.hstack((left, right))


class ActPlanProcessor:
    def __init__(self, title: str) -> None:
        self._preview = TkImagePreviewThread(title)
        self._preview.start()

    def process_snapshot(self, top_b64: str, side_b64: str) -> None:
        top = decode_b64_jpeg(top_b64)
        side = decode_b64_jpeg(side_b64)
        left = top if top is not None else _placeholder_bgr("no Cam_Top")
        right = side if side is not None else _placeholder_bgr("no Cam_Side")
        self._preview.set_frame(_hstack_left_right(left, right))

    def close(self) -> None:
        self._preview.stop()
