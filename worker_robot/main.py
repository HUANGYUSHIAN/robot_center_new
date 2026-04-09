from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

import psutil
from rich.console import Console
from rich.live import Live
from rich.table import Table

from robot_control import RobotControlRuntime, SIM_STEP_HZ
from websocket import SharedData, ws_thread_main

try:
    import pynvml
except Exception:  # pragma: no cover
    pynvml = None

console = Console()
SHOW_RICH = False
_TMUI_ROOT = Path(__file__).resolve().parent.parent
if str(_TMUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_TMUI_ROOT))
from tmui_discovery import resolve_server_endpoint  # noqa: E402

_log = logging.getLogger("tmui.worker_robot")
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.client").setLevel(logging.WARNING)

robot_state = {
    "server": "N/A",
    "digital_on": False,
    "status_on": False,
    "digital_frames": 0,
    "status_updates": 0,
    "top_frames": 0,
    "side_frames": 0,
    "dof_count": 0,
    "last_error": "",
}


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
    table = Table(title="worker_robot (Isaac) 即時狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("server", str(robot_state["server"]))
    table.add_row("DOF 數量", str(robot_state["dof_count"]))
    table.add_row("Digital 訂閱", "開啟" if robot_state["digital_on"] else "關閉")
    table.add_row("Status 訂閱", "開啟" if robot_state["status_on"] else "關閉")
    table.add_row("Digital frame", str(robot_state["digital_frames"]))
    table.add_row("Cam_Top frame", str(robot_state["top_frames"]))
    table.add_row("Cam_Side frame", str(robot_state["side_frames"]))
    table.add_row("Status 更新", str(robot_state["status_updates"]))
    if robot_state["last_error"]:
        table.add_row("最後錯誤", str(robot_state["last_error"]))
    table.add_row("RAM MB(avg/max)", f"{resource_monitor.ram_avg:.1f} / {resource_monitor.ram_max:.1f}")
    if resource_monitor.gpu_available:
        table.add_row("GPU %(avg/max)", f"{resource_monitor.gpu_avg:.1f} / {resource_monitor.gpu_max:.1f}")
        table.add_row("VRAM MB(avg/max)", f"{resource_monitor.vram_avg:.1f} / {resource_monitor.vram_max:.1f}")
    else:
        table.add_row("GPU", "No GPU")
        table.add_row("VRAM", "No GPU")
    return table


if __name__ == "__main__":
    server_ip, server_port = resolve_server_endpoint("worker_robot")
    robot_state["server"] = f"{server_ip}:{server_port}"
    _log.info("使用 server -> %s", robot_state["server"])
    shared = SharedData()
    runtime = RobotControlRuntime(scene_dir=Path(__file__).resolve().parent)
    with shared.lock:
        shared.joint_names = list(runtime.dof_names)
        shared.joint_values = [0.0 for _ in runtime.dof_names]
        shared.real_object_init_list = list(runtime.real_object_list_init)
        pose, sim_t = runtime.get_real_object_pose_update()
        shared.real_object_pose_update = pose
        shared.simulation_time = sim_t

    ws_thread = threading.Thread(
        target=ws_thread_main,
        args=(server_ip, str(server_port), shared, robot_state),
        daemon=True,
    )
    ws_thread.start()

    live = Live(build_table(), console=console, refresh_per_second=4, transient=False) if SHOW_RICH else None
    if live is not None:
        live.start(refresh=True)
    try:
        while True:
            runtime.step()
            with shared.lock:
                shared.joint_values = runtime.get_joint_values()
                shared.latest_digital = runtime.get_digital_frame()
                shared.latest_top = runtime.get_top_frame()
                shared.latest_side = runtime.get_side_frame()
                pose, sim_t = runtime.get_real_object_pose_update()
                shared.real_object_pose_update = pose
                shared.simulation_time = sim_t
                if shared.stop:
                    break
            if live is not None:
                live.update(build_table(), refresh=True)
            time.sleep(1 / SIM_STEP_HZ)
    except KeyboardInterrupt:
        pass
    finally:
        with shared.lock:
            shared.stop = True
        ws_thread.join(timeout=2.0)
        runtime.close()
        if live is not None:
            live.stop()
