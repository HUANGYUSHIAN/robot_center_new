from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

import websockets

# 與 robot_control.SIM_STEP_HZ 一致（避免 websocket 依賴載入 Isaac）
REAL_OBJECT_POSE_HZ = 60

_TMUI_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TMUI_ROOT / "server"))
from contracts import Event  # noqa: E402

DIGITAL_FPS = 4
TOP_FPS = 4
STATUS_HZ = 2


class SharedData:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.stop = False
        self.digital_on = False
        self.status_on = False
        self.latest_digital = ""
        self.latest_top = ""
        self.latest_side = ""
        self.joint_names: list[str] = []
        self.joint_values: list[float] = []
        self.real_object_init_list: list[dict] | None = None
        self.real_object_pose_update: list[dict] | None = None
        self.simulation_time: float = 0.0


async def ws_worker(ip: str, port: str, shared: SharedData, state: dict) -> None:
    uri = f"ws://{ip}:{port}/ws"
    sent_status_init = False
    while True:
        with shared.lock:
            if shared.stop:
                return
        try:
            async with websockets.connect(uri, open_timeout=8) as ws:
                await ws.send(json.dumps({"event": Event.REGISTER, "role": "worker_robot"}, ensure_ascii=False))
                await ws.recv()
                sent_status_init = False

                async def recv_loop() -> None:
                    while True:
                        msg = json.loads(await ws.recv())
                        evt = msg.get("event")
                        view = msg.get("view")
                        if evt == Event.SUBSCRIBE_VIEW and view == "digital":
                            with shared.lock:
                                shared.digital_on = True
                            await ws.send(
                                json.dumps({"event": Event.VIEW_STATUS, "view": "digital", "status": "streaming"}, ensure_ascii=False)
                            )
                        elif evt == Event.UNSUBSCRIBE_VIEW and view == "digital":
                            with shared.lock:
                                shared.digital_on = False
                            await ws.send(json.dumps({"event": Event.VIEW_STATUS, "view": "digital", "status": "idle"}, ensure_ascii=False))
                        elif evt == Event.SUBSCRIBE_VIEW and view == "robot_status":
                            with shared.lock:
                                shared.status_on = True
                            await ws.send(
                                json.dumps(
                                    {"event": Event.VIEW_STATUS, "view": "robot_status", "status": "streaming"},
                                    ensure_ascii=False,
                                )
                            )
                        elif evt == Event.UNSUBSCRIBE_VIEW and view == "robot_status":
                            with shared.lock:
                                shared.status_on = False
                            await ws.send(
                                json.dumps({"event": Event.VIEW_STATUS, "view": "robot_status", "status": "idle"}, ensure_ascii=False)
                            )

                async def digital_sender() -> None:
                    while True:
                        with shared.lock:
                            enabled = shared.digital_on
                            frame = shared.latest_digital
                        state["digital_on"] = enabled
                        if enabled and frame:
                            await ws.send(json.dumps({"event": Event.FRAME, "view": "digital", "image": frame}, ensure_ascii=False))
                            state["digital_frames"] += 1
                        await asyncio.sleep(1 / DIGITAL_FPS)

                async def top_sender() -> None:
                    while True:
                        with shared.lock:
                            top_frame = shared.latest_top
                            side_frame = shared.latest_side
                        if top_frame:
                            await ws.send(json.dumps({"event": Event.FRAME, "view": "camera_top", "image": top_frame}, ensure_ascii=False))
                            state["top_frames"] += 1
                        if side_frame:
                            await ws.send(json.dumps({"event": Event.FRAME, "view": "camera_side", "image": side_frame}, ensure_ascii=False))
                            state["side_frames"] += 1
                        await asyncio.sleep(1 / TOP_FPS)

                async def real_object_sender() -> None:
                    init_sent = False
                    tick = 1.0 / float(REAL_OBJECT_POSE_HZ)
                    while True:
                        with shared.lock:
                            stopping = shared.stop
                            init_list = shared.real_object_init_list
                            pose_upd = shared.real_object_pose_update
                            sim_t = float(shared.simulation_time)
                        if stopping:
                            return
                        if init_list and not init_sent:
                            await ws.send(
                                json.dumps(
                                    {"event": Event.REAL_OBJECT_LIST_INIT, "objects": list(init_list)},
                                    ensure_ascii=False,
                                )
                            )
                            init_sent = True
                        if init_sent and pose_upd is not None:
                            await ws.send(
                                json.dumps(
                                    {
                                        "event": Event.REAL_OBJECT_UPDATE,
                                        "sim_time": sim_t,
                                        "objects": list(pose_upd),
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        await asyncio.sleep(tick)

                async def status_sender() -> None:
                    nonlocal sent_status_init
                    while True:
                        with shared.lock:
                            enabled = shared.status_on
                            names = list(shared.joint_names)
                            vals = list(shared.joint_values)
                        state["status_on"] = enabled
                        if enabled:
                            if not sent_status_init:
                                await ws.send(
                                    json.dumps(
                                        {"event": Event.ROBOT_STATUS_INIT, "view": "robot_status", "joints": names},
                                        ensure_ascii=False,
                                    )
                                )
                                sent_status_init = True
                            await ws.send(
                                json.dumps(
                                    {"event": Event.ROBOT_STATUS_UPDATE, "view": "robot_status", "angles": vals},
                                    ensure_ascii=False,
                                )
                            )
                            state["status_updates"] += 1
                        else:
                            sent_status_init = False
                        await asyncio.sleep(1 / STATUS_HZ)

                tasks = [
                    asyncio.create_task(recv_loop()),
                    asyncio.create_task(digital_sender()),
                    asyncio.create_task(top_sender()),
                    asyncio.create_task(status_sender()),
                    asyncio.create_task(real_object_sender()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
        except Exception as exc:
            state["last_error"] = str(exc)
            await asyncio.sleep(2.0)


def ws_thread_main(ip: str, port: str, shared: SharedData, state: dict) -> None:
    asyncio.run(ws_worker(ip, port, shared, state))
