from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import psutil
import websockets
from rich.console import Console
from rich.live import Live
from rich.table import Table

try:
    import pynvml
except Exception:  # pragma: no cover
    pynvml = None

F_update = 10.0
SHOW_RICH = False

console = Console()
_TMUI_ROOT = Path(__file__).resolve().parent.parent
if str(_TMUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_TMUI_ROOT))
sys.path.insert(0, str(_TMUI_ROOT / "server"))
from contracts import Event  # noqa: E402
from tmui_discovery import resolve_server_endpoint  # noqa: E402
from tmui_tk_preview import TkImagePreviewThread  # noqa: E402

state = {"pulls": 0, "source_ok": False, "server": "N/A"}
_log = logging.getLogger("tmui.worker_vision")
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)


class ResourceMonitor:
    def __init__(self) -> None:
        self.samples = 0
        self.ram_avg = 0.0
        self.ram_max = 0.0
        self.gpu_avg = 0.0
        self.gpu_max = 0.0
        self.vram_avg = 0.0
        self.vram_max = 0.0
        self.gpu_available = False
        self._proc = psutil.Process(os.getpid())
        self._gpu_handle = None
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                if pynvml.nvmlDeviceGetCount() > 0:
                    self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self.gpu_available = True
            except Exception:
                self.gpu_available = False

    def _avg(self, prev: float, value: float) -> float:
        return ((prev * self.samples) + value) / (self.samples + 1)

    def update(self) -> None:
        rss_mb = self._proc.memory_info().rss / (1024 * 1024)
        self.ram_avg = self._avg(self.ram_avg, rss_mb)
        self.ram_max = max(self.ram_max, rss_mb)
        if self.gpu_available and self._gpu_handle is not None:
            try:
                util = float(pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle).gpu)
                mem = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                vram_mb = mem.used / (1024 * 1024)
                self.gpu_avg = self._avg(self.gpu_avg, util)
                self.gpu_max = max(self.gpu_max, util)
                self.vram_avg = self._avg(self.vram_avg, vram_mb)
                self.vram_max = max(self.vram_max, vram_mb)
            except Exception:
                self.gpu_available = False
        self.samples += 1


resource_monitor = ResourceMonitor()


def build_table() -> Table:
    resource_monitor.update()
    table = Table(title="worker_vision 狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("server", str(state["server"]))
    table.add_row("F_update (s)", str(F_update))
    table.add_row("快照次數", str(state["pulls"]))
    table.add_row("有影像資料", "是" if state["source_ok"] else "否")
    table.add_row("RAM MB(avg/max)", f"{resource_monitor.ram_avg:.1f} / {resource_monitor.ram_max:.1f}")
    if resource_monitor.gpu_available:
        table.add_row("GPU %(avg/max)", f"{resource_monitor.gpu_avg:.1f} / {resource_monitor.gpu_max:.1f}")
        table.add_row("VRAM MB(avg/max)", f"{resource_monitor.vram_avg:.1f} / {resource_monitor.vram_max:.1f}")
    else:
        table.add_row("GPU", "No GPU")
        table.add_row("VRAM", "No GPU")
    return table


def decode_b64_jpeg(image_b64: str) -> np.ndarray | None:
    if not image_b64:
        return None
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        return None
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _bgr_to_gray3(bgr: np.ndarray | None, placeholder: str) -> np.ndarray:
    if bgr is None or bgr.size == 0:
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(img, placeholder, (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 2)
        return img
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _hstack_left_right(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    h = min(left.shape[0], right.shape[0])
    if left.shape[0] != h:
        left = cv2.resize(left, (int(left.shape[1] * h / left.shape[0]), h), interpolation=cv2.INTER_AREA)
    if right.shape[0] != h:
        right = cv2.resize(right, (int(right.shape[1] * h / right.shape[0]), h), interpolation=cv2.INTER_AREA)
    return np.hstack((left, right))


async def run(ip: str, port: str) -> None:
    uri = f"ws://{ip}:{port}/ws"
    incoming: asyncio.Queue = asyncio.Queue()

    async with websockets.connect(uri, open_timeout=8) as ws:
        await ws.send(json.dumps({"event": Event.REGISTER, "role": "worker_vision"}, ensure_ascii=False))
        await ws.recv()
        _log.info("worker_vision 註冊成功")

        async def reader() -> None:
            while True:
                raw = await ws.recv()
                await incoming.put(json.loads(raw))

        read_task = asyncio.create_task(reader())
        preview = TkImagePreviewThread("worker_vision: Cam_Top (左) | Cam_Side (右) [灰階]")
        preview.start()
        try:
            while True:
                await asyncio.sleep(F_update)
                await ws.send(json.dumps({"event": Event.CAMERA_SNAPSHOT_REQUEST}, ensure_ascii=False))
                while True:
                    try:
                        msg = await asyncio.wait_for(incoming.get(), timeout=60.0)
                    except asyncio.TimeoutError:
                        _log.warning("等待 camera_snapshot 逾時")
                        break
                    if msg.get("event") == Event.CAMERA_SNAPSHOT:
                        top_b64 = str(msg.get("top", ""))
                        side_b64 = str(msg.get("side", ""))
                        if not top_b64 and not side_b64:
                            _log.warning(
                                "camera_snapshot 的 top/side 皆為空（請確認 worker_robot 已連線並送出 camera_top/camera_side）"
                            )
                        top = decode_b64_jpeg(top_b64)
                        side = decode_b64_jpeg(side_b64)
                        left = _bgr_to_gray3(top, "no Cam_Top")
                        right = _bgr_to_gray3(side, "no Cam_Side")
                        combined = _hstack_left_right(left, right)
                        preview.set_frame(combined)
                        state["pulls"] += 1
                        state["source_ok"] = top is not None or side is not None
                        break
        finally:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await read_task
            preview.stop()


if __name__ == "__main__":
    server_ip, server_port = resolve_server_endpoint("worker_vision")
    state["server"] = f"{server_ip}:{server_port}"
    _log.info("使用 server -> %s", state["server"])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    live = Live(build_table(), console=console, refresh_per_second=4) if SHOW_RICH else None
    if live is not None:
        live.start()

    async def refresh_live() -> None:
        while True:
            if live is not None:
                live.update(build_table())
            await asyncio.sleep(0.5)

    refresh_task = None
    if SHOW_RICH:
        refresh_task = loop.create_task(refresh_live())
    try:
        loop.run_until_complete(run(server_ip, str(server_port)))
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                loop.run_until_complete(refresh_task)
        if live is not None:
            live.stop()
        loop.close()
