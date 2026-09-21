"""Generic WebSocket gateway for channel subscriptions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from generation.exceptions import GenerationError
from generation.manager import get_generation_manager


router = APIRouter(tags=["realtime"])


async def _send_loop(
    websocket: WebSocket,
    outbound: asyncio.Queue[dict[str, Any]],
) -> None:
    while True:
        try:
            payload = await asyncio.wait_for(outbound.get(), timeout=20)
        except asyncio.TimeoutError:
            payload = {
                "type": "heartbeat",
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
        await websocket.send_json(payload)


async def _forward_events(
    channel: str,
    resource_id: str,
    queue: asyncio.Queue,
    outbound: asyncio.Queue[dict[str, Any]],
) -> None:
    manager = get_generation_manager()
    try:
        while True:
            payload = await queue.get()
            await outbound.put(payload)
            job = payload.get("job") or {}
            if job.get("status") in {"completed", "failed", "cancelled"}:
                return
    finally:
        manager.unsubscribe(channel, resource_id, queue)


@router.websocket("/api/ws")
async def realtime_websocket(websocket: WebSocket) -> None:
    """Accept channel subscriptions over one multiplexed WebSocket."""

    await websocket.accept()
    manager = get_generation_manager()
    outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    subscriptions: dict[
        tuple[str, str],
        tuple[asyncio.Queue, asyncio.Task],
    ] = {}
    sender = asyncio.create_task(_send_loop(websocket, outbound))

    await outbound.put(
        {
            "type": "connected",
            "protocol": "material-copilot.realtime.v1",
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")
            request_id = message.get("request_id")

            if action == "ping":
                await outbound.put(
                    {
                        "type": "pong",
                        "request_id": request_id,
                        "server_time": datetime.now(timezone.utc).isoformat(),
                    }
                )
                continue

            channel = message.get("channel")
            resource_id = message.get("resource_id")

            if action == "unsubscribe":
                key = (str(channel), str(resource_id))
                subscription = subscriptions.pop(key, None)
                if subscription:
                    queue, task = subscription
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    manager.unsubscribe(key[0], key[1], queue)
                await outbound.put(
                    {
                        "type": "unsubscribed",
                        "channel": channel,
                        "resource_id": resource_id,
                        "request_id": request_id,
                    }
                )
                continue

            if action != "subscribe":
                await outbound.put(
                    {
                        "type": "error",
                        "code": "INVALID_ACTION",
                        "message": f"不支持的 WebSocket 操作：{action}",
                        "request_id": request_id,
                    }
                )
                continue

            if channel != "generation.job" or not resource_id:
                await outbound.put(
                    {
                        "type": "error",
                        "code": "INVALID_SUBSCRIPTION",
                        "message": "当前仅支持 generation.job 频道。",
                        "request_id": request_id,
                    }
                )
                continue

            try:
                job = await manager.get_job(str(resource_id))
            except GenerationError as exc:
                await outbound.put(
                    {
                        "type": "error",
                        "code": exc.code,
                        "message": exc.message,
                        "request_id": request_id,
                    }
                )
                continue

            key = (str(channel), str(resource_id))
            if key not in subscriptions:
                queue = manager.subscribe(key[0], key[1])
                task = asyncio.create_task(
                    _forward_events(key[0], key[1], queue, outbound)
                )
                subscriptions[key] = (queue, task)

            await outbound.put(
                {
                    "type": "subscribed",
                    "channel": channel,
                    "resource_id": resource_id,
                    "request_id": request_id,
                }
            )
            await outbound.put(
                {
                    "type": "snapshot",
                    "channel": channel,
                    "resource_id": resource_id,
                    "job": job.model_dump(mode="json"),
                    "server_time": datetime.now(timezone.utc).isoformat(),
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        for (channel, resource_id), (queue, task) in subscriptions.items():
            task.cancel()
            manager.unsubscribe(channel, resource_id, queue)
        await asyncio.gather(
            *(task for _, task in subscriptions.values()),
            return_exceptions=True,
        )
