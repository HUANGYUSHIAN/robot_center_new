"""以 cv2 白底繪製文字、Pillow+Tkinter 顯示 Real_Object_list（關閉視窗不影響 server）。"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageTk

F_update = 10.0

_log = logging.getLogger("tmui.server")


def _format_objects_lines(objects: list[dict[str, Any]]) -> list[str]:
    if not objects:
        return ["Real_Object_list: (empty)"]
    lines: list[str] = []
    for obj in objects:
        dtype = str(obj.get("datatype", "?"))
        name = str(obj.get("name", ""))
        lines.append(f"=== {dtype} / {name} ===")
        lines.append(f"  prim: {obj.get('prim', '')}")
        lines.append(f"  color: {obj.get('color', '')}")
        if dtype == "Cube":
            lines.append(f"  Lcube: {obj.get('Lcube')}  Wcube: {obj.get('Wcube')}  Hcube: {obj.get('Hcube')}")
        elif dtype == "Sphere":
            lines.append(f"  Radius: {obj.get('Radius')}")
        c = obj.get("center", "")
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            lines.append(f"  center: [{float(c[0]):.4f}, {float(c[1]):.4f}, {float(c[2]):.4f}]")
        else:
            lines.append(f"  center: {c}")
        lines.append("")
    return lines


def _render_bgr(lines: list[str], sim_time_sec: float) -> np.ndarray:
    line_h = 26
    pad = 24
    w = 760
    h = max(200, pad * 2 + line_h * len(lines))
    img = np.ones((h, w, 3), dtype=np.uint8) * 255
    y = pad
    for line in lines:
        s = line if len(line) <= 95 else line[:92] + "..."
        cv2.putText(img, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
        y += line_h
    time_text = f"sim t = {float(sim_time_sec):.4f} s"
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.62
    thick = 2
    (tw, th), _ = cv2.getTextSize(time_text, font, scale, thick)
    cv2.putText(
        img,
        time_text,
        (w - pad - tw, pad + th),
        font,
        scale,
        (0, 0, 160),
        thick,
        cv2.LINE_AA,
    )
    return img


def start_real_object_debug_thread(hub: Any) -> threading.Thread:
    interval = max(0.2, 1.0 / float(F_update))

    def run() -> None:
        try:
            import tkinter as tk
        except Exception as exc:
            _log.warning("Real_Object_list 視窗略過（無法載入 tkinter）: %s", exc)
            return

        visible = [True]
        try:
            root = tk.Tk()
        except Exception as exc:
            _log.warning("Real_Object_list 視窗略過（可能無圖形環境）: %s", exc)
            return
        root.title("TMUI server — Real_Object_list")
        label = tk.Label(root)
        label.pack()
        photo_ref: list[ImageTk.PhotoImage | None] = [None]

        def on_close() -> None:
            visible[0] = False
            with contextlib.suppress(Exception):
                root.withdraw()

        root.protocol("WM_DELETE_WINDOW", on_close)

        def tick() -> None:
            try:
                objs, sim_t = hub.snapshot_real_object_debug()
                lines = _format_objects_lines(objs)
                if visible[0]:
                    bgr = _render_bgr(lines, sim_t)
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    im = Image.fromarray(rgb)
                    photo = ImageTk.PhotoImage(image=im)
                    label.configure(image=photo)
                    photo_ref[0] = photo
            except Exception:
                pass
            root.after(int(interval * 1000), tick)

        root.after(10, tick)
        try:
            root.mainloop()
        except Exception as exc:
            _log.warning("Real_Object_list 視窗結束: %s", exc)

    t = threading.Thread(target=run, name="RealObjectDebugView", daemon=True)
    t.start()
    return t
