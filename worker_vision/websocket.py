from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

import websockets

from process import VisionProcessor

_log = logging.getLogger("tmui.worker_vision")


async def run_worker(ip: str, port: str, f_update: float, state: dict[str, Any], event: Any) -> None:
    uri = f"ws://{ip}:{port}/ws"
    incoming: asyncio.Queue = asyncio.Queue()

    async with websockets.connect(uri, open_timeout=8) as ws:
        await ws.send(json.dumps({"event": event.REGISTER, "role": "worker_vision"}, ensure_ascii=False))
        await ws.recv()
        _log.info("worker_vision 註冊成功")

        async def reader() -> None:
            while True:
                raw = await ws.recv()
                await incoming.put(json.loads(raw))

        read_task = asyncio.create_task(reader())
        processor = VisionProcessor("worker_vision: Cam_Top (左) | Cam_Side (右) [灰階]")
        try:
            while True:
                await asyncio.sleep(f_update)
                await ws.send(json.dumps({"event": event.CAMERA_SNAPSHOT_REQUEST}, ensure_ascii=False))
                while True:
                    try:
                        msg = await asyncio.wait_for(incoming.get(), timeout=60.0)
                    except asyncio.TimeoutError:
                        _log.warning("等待 camera_snapshot 逾時")
                        break
                    if msg.get("event") == event.CAMERA_SNAPSHOT:
                        top_b64 = str(msg.get("top", ""))
                        side_b64 = str(msg.get("side", ""))
                        if not top_b64 and not side_b64:
                            _log.warning(
                                "camera_snapshot 的 top/side 皆為空（請確認 worker_robot 已連線並送出 camera_top/camera_side）"
                            )
                        state["source_ok"] = processor.process_snapshot(top_b64, side_b64)
                        state["pulls"] += 1
                        break
        finally:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await read_task
            processor.close()
