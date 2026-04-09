from __future__ import annotations

import asyncio
import json
import threading

import websockets

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


async def ws_worker(ip: str, port: str, shared: SharedData, state: dict) -> None:
    uri = f"ws://{ip}:{port}/ws"
    sent_status_init = False
    while True:
        with shared.lock:
            if shared.stop:
                return
        try:
            async with websockets.connect(uri, open_timeout=8) as ws:
                await ws.send(json.dumps({"event": "register", "role": "worker_robot"}, ensure_ascii=False))
                await ws.recv()
                sent_status_init = False

                async def recv_loop() -> None:
                    while True:
                        msg = json.loads(await ws.recv())
                        evt = msg.get("event")
                        view = msg.get("view")
                        if evt == "subscribe_view" and view == "digital":
                            with shared.lock:
                                shared.digital_on = True
                            await ws.send(
                                json.dumps({"event": "view_status", "view": "digital", "status": "streaming"}, ensure_ascii=False)
                            )
                        elif evt == "unsubscribe_view" and view == "digital":
                            with shared.lock:
                                shared.digital_on = False
                            await ws.send(json.dumps({"event": "view_status", "view": "digital", "status": "idle"}, ensure_ascii=False))
                        elif evt == "subscribe_view" and view == "robot_status":
                            with shared.lock:
                                shared.status_on = True
                            await ws.send(
                                json.dumps(
                                    {"event": "view_status", "view": "robot_status", "status": "streaming"},
                                    ensure_ascii=False,
                                )
                            )
                        elif evt == "unsubscribe_view" and view == "robot_status":
                            with shared.lock:
                                shared.status_on = False
                            await ws.send(
                                json.dumps({"event": "view_status", "view": "robot_status", "status": "idle"}, ensure_ascii=False)
                            )

                async def digital_sender() -> None:
                    while True:
                        with shared.lock:
                            enabled = shared.digital_on
                            frame = shared.latest_digital
                        state["digital_on"] = enabled
                        if enabled and frame:
                            await ws.send(json.dumps({"event": "frame", "view": "digital", "image": frame}, ensure_ascii=False))
                            state["digital_frames"] += 1
                        await asyncio.sleep(1 / DIGITAL_FPS)

                async def top_sender() -> None:
                    while True:
                        with shared.lock:
                            top_frame = shared.latest_top
                            side_frame = shared.latest_side
                        if top_frame:
                            await ws.send(json.dumps({"event": "frame", "view": "camera_top", "image": top_frame}, ensure_ascii=False))
                            state["top_frames"] += 1
                        if side_frame:
                            await ws.send(json.dumps({"event": "frame", "view": "camera_side", "image": side_frame}, ensure_ascii=False))
                            state["side_frames"] += 1
                        await asyncio.sleep(1 / TOP_FPS)

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
                                        {"event": "robot_status_init", "view": "robot_status", "joints": names},
                                        ensure_ascii=False,
                                    )
                                )
                                sent_status_init = True
                            await ws.send(
                                json.dumps(
                                    {"event": "robot_status_update", "view": "robot_status", "angles": vals},
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
