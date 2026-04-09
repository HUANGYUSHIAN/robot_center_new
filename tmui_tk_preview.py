"""以 Tkinter + Pillow 顯示 BGR 影像，避免 opencv-python 內建 Qt 後端的字型路徑問題。"""

from __future__ import annotations

import queue
import threading

import cv2
import numpy as np
from PIL import Image, ImageTk


class TkImagePreviewThread:
    """在獨立執行緒跑 Tk mainloop；set_frame 可從 asyncio 執行緒安全呼叫。"""

    def __init__(self, title: str, max_display_width: int = 1280) -> None:
        self._title = title
        self._max_w = max_display_width
        self._q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=3)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="TkImagePreview", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def set_frame(self, bgr: np.ndarray | None) -> None:
        if bgr is None or bgr.size == 0:
            return
        h, w = bgr.shape[:2]
        if w > self._max_w:
            scale = self._max_w / w
            bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        try:
            self._q.put_nowait(bgr.copy())
        except queue.Full:
            try:
                while True:
                    self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait(bgr.copy())
            except queue.Full:
                pass

    def stop(self) -> None:
        self._stop.set()
        try:
            self._q.put_nowait(None)
        except Exception:
            pass
        self._thread.join(timeout=6.0)

    def _run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.title(self._title)
        label = tk.Label(root)
        label.pack()
        photo_ref: list[ImageTk.PhotoImage | None] = [None]

        def tick() -> None:
            if self._stop.is_set():
                root.destroy()
                return
            latest: np.ndarray | None = None
            try:
                while True:
                    item = self._q.get_nowait()
                    if item is None:
                        root.destroy()
                        return
                    latest = item
            except queue.Empty:
                pass
            if latest is not None:
                rgb = cv2.cvtColor(latest, cv2.COLOR_BGR2RGB)
                im = Image.fromarray(rgb)
                photo = ImageTk.PhotoImage(image=im)
                label.configure(image=photo)
                photo_ref[0] = photo
            root.after(33, tick)

        root.after(33, tick)
        root.mainloop()
