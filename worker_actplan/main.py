from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

import psutil
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
_log = logging.getLogger("tmui.worker_actplan")
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)

_TMUI_ROOT = Path(__file__).resolve().parent.parent
if str(_TMUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_TMUI_ROOT))
sys.path.insert(0, str(_TMUI_ROOT / "server"))
from contracts import Event  # noqa: E402
from tmui_discovery import resolve_server_endpoint  # noqa: E402
from websocket import now_text, run_worker  # noqa: E402

state = {"requests": 0, "replies": 0, "pulls": 0, "server": "N/A"}


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
    table = Table(title="worker_actplan 狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("server", state["server"])
    table.add_row("F_update (s)", str(F_update))
    table.add_row("指令請求", str(state["requests"]))
    table.add_row("指令回覆", str(state["replies"]))
    table.add_row("相機快照次數", str(state["pulls"]))
    table.add_row("RAM MB(avg/max)", f"{resource_monitor.ram_avg:.1f} / {resource_monitor.ram_max:.1f}")
    if resource_monitor.gpu_available:
        table.add_row("GPU %(avg/max)", f"{resource_monitor.gpu_avg:.1f} / {resource_monitor.gpu_max:.1f}")
        table.add_row("VRAM MB(avg/max)", f"{resource_monitor.vram_avg:.1f} / {resource_monitor.vram_max:.1f}")
    else:
        table.add_row("GPU", "No GPU")
        table.add_row("VRAM", "No GPU")
    return table


if __name__ == "__main__":
    server_ip, server_port = resolve_server_endpoint("worker_actplan")
    state["server"] = f"{server_ip}:{server_port}"
    console.print(f"[cyan]{now_text()}[/cyan] 使用 server -> {state['server']}")

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
        loop.run_until_complete(run_worker(server_ip, str(server_port), F_update, state, Event, console))
    except Exception as exc:
        console.print(f"[red]{now_text()}[/red] 連線失敗或中斷: {exc}")
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                loop.run_until_complete(refresh_task)
        if live is not None:
            live.stop()
        loop.close()
