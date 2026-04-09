from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from typing import Any

import websockets
from rich.console import Console

from process import ActPlanProcessor

_log = logging.getLogger("tmui.worker_actplan")


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


async def handle_command(ws: Any, text: str, state: dict[str, Any], console: Console, event: Any) -> None:
    console.print(f"[yellow]{now_text()}[/yellow] 收到請求: {text}")
    state["requests"] += 1
    await asyncio.sleep(2)
    reply = text[: len(text) // 2] if text else ""
    await ws.send(json.dumps({"event": event.COMMAND_REPLY, "role": "assistant", "text": reply}, ensure_ascii=False))
    console.print(f"[green]{now_text()}[/green] 已回覆: {reply}")
    state["replies"] += 1


async def run_worker(
    ip: str,
    port: str,
    f_update: float,
    state: dict[str, Any],
    event: Any,
    console: Console,
) -> None:
    uri = f"ws://{ip}:{port}/ws"
    incoming: asyncio.Queue = asyncio.Queue()
    console.print(f"[cyan]{now_text()}[/cyan] 連線到 {uri}")

    async with websockets.connect(uri, open_timeout=8) as ws:
        await ws.send(json.dumps({"event": event.REGISTER, "role": "worker_actplan"}, ensure_ascii=False))
        ack = json.loads(await ws.recv())
        console.print(f"[green]{now_text()}[/green] 註冊成功: {ack}")

        async def reader() -> None:
            while True:
                raw = await ws.recv()
                await incoming.put(json.loads(raw))

        read_task = asyncio.create_task(reader())
        processor = ActPlanProcessor("worker_actplan: Cam_Top (左) | Cam_Side (右)")
        next_snap = asyncio.get_event_loop().time() + f_update

        try:
            while True:
                loop_time = asyncio.get_event_loop().time()
                delay = next_snap - loop_time
                msg = None
                if delay > 0:
                    try:
                        msg = await asyncio.wait_for(incoming.get(), timeout=delay)
                    except asyncio.TimeoutError:
                        msg = None
                else:
                    try:
                        msg = incoming.get_nowait()
                    except asyncio.QueueEmpty:
                        msg = None

                if msg is not None:
                    evt = msg.get("event")
                    if evt == event.COMMAND_INPUT:
                        await handle_command(ws, str(msg.get("text", "")), state, console, event)
                    elif evt == event.CAMERA_SNAPSHOT:
                        top_b64 = str(msg.get("top", ""))
                        side_b64 = str(msg.get("side", ""))
                        if not top_b64 and not side_b64:
                            _log.warning(
                                "camera_snapshot 的 top/side 皆為空（請確認 worker_robot 已連線並送出 camera_top/camera_side）"
                            )
                        processor.process_snapshot(top_b64, side_b64)
                        state["pulls"] += 1

                loop_time = asyncio.get_event_loop().time()
                if loop_time >= next_snap:
                    await ws.send(json.dumps({"event": event.CAMERA_SNAPSHOT_REQUEST}, ensure_ascii=False))
                    next_snap = loop_time + f_update
        finally:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await read_task
            processor.close()
