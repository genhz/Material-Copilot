"""Generic WebSocket gateway for channel subscriptions."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent_workflow.service import get_agent_workflow_service
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
            campaign = payload.get("campaign") or {}
            resource = job or campaign
            if resource.get("status") in {
                "completed",
                "partial",
                "failed",
                "cancelled",
            }:
                return
    finally:
        manager.unsubscribe(channel, resource_id, queue)


async def _forward_agent_events(
    session_id: str,
    queue: asyncio.Queue,
    outbound: asyncio.Queue[dict[str, Any]],
) -> None:
    service = get_agent_workflow_service()
    try:
        while True:
            await outbound.put(await queue.get())
    finally:
        service.unsubscribe(session_id, queue)


@router.websocket("/api/ws")
async def realtime_websocket(websocket: WebSocket) -> None:
    """Accept channel subscriptions over one multiplexed WebSocket."""

    await websocket.accept()
    manager = get_generation_manager()
    agent_workflow = get_agent_workflow_service()
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

            if action and action.startswith("agent."):
                session_id = str(message.get("session_id") or "")
                if not session_id:
                    await outbound.put(
                        {
                            "type": "error",
                            "code": "SESSION_REQUIRED",
                            "message": "Agent 操作需要 session_id。",
                            "request_id": request_id,
                        }
                    )
                    continue

                if action == "agent.message":
                    await agent_workflow.handle_message(
                        session_id,
                        str(message.get("message") or ""),
                    )
                elif action == "agent.revise":
                    await agent_workflow.revise_plan(
                        session_id,
                        str(message.get("plan_id") or ""),
                        int(message.get("revision") or 0),
                        str(message.get("message") or ""),
                    )
                elif action == "agent.confirm":
                    await agent_workflow.confirm_plan(
                        session_id,
                        str(message.get("plan_id") or ""),
                        int(message.get("revision") or 0),
                    )
                elif action == "agent.cancel":
                    await agent_workflow.cancel_workflow(session_id)
                elif action == "agent.clear":
                    await agent_workflow.clear_session(session_id)
                elif action == "agent.snapshot":
                    await outbound.put(
                        {
                            "type": "agent.snapshot",
                            "channel": "agent.session",
                            "resource_id": session_id,
                            "request_id": request_id,
                            "snapshot": agent_workflow.snapshot(
                                session_id,
                                int(message.get("last_sequence") or 0),
                            ),
                        }
                    )
                else:
                    await outbound.put(
                        {
                            "type": "error",
                            "code": "INVALID_AGENT_ACTION",
                            "message": f"不支持的 Agent 操作：{action}",
                            "request_id": request_id,
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
                    if key[0] == "agent.session":
                        agent_workflow.unsubscribe(key[1], queue)
                    else:
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

            if channel not in {
                "generation.job",
                "generation.campaign",
                "agent.session",
            } or not resource_id:
                await outbound.put(
                    {
                        "type": "error",
                        "code": "INVALID_SUBSCRIPTION",
                        "message": "不支持的实时订阅频道。",
                        "request_id": request_id,
                    }
                )
                continue

            resource = None
            resource_key = ""
            if channel != "agent.session":
                try:
                    if channel == "generation.job":
                        resource = await manager.get_job(str(resource_id))
                        resource_key = "job"
                    else:
                        resource = await manager.get_campaign(str(resource_id))
                        resource_key = "campaign"
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
                if channel == "agent.session":
                    queue = agent_workflow.subscribe(key[1])
                    task = asyncio.create_task(
                        _forward_agent_events(key[1], queue, outbound)
                    )
                else:
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
            if channel == "agent.session":
                await outbound.put(
                    {
                        "type": "agent.snapshot",
                        "channel": channel,
                        "resource_id": resource_id,
                        "snapshot": agent_workflow.snapshot(str(resource_id)),
                    }
                )
                continue

            assert resource is not None
            await outbound.put(
                {
                    "type": "snapshot",
                    "channel": channel,
                    "resource_id": resource_id,
                    resource_key: resource.model_dump(mode="json"),
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
            if channel == "agent.session":
                agent_workflow.unsubscribe(resource_id, queue)
            else:
                manager.unsubscribe(channel, resource_id, queue)
        await asyncio.gather(
            *(task for _, task in subscriptions.values()),
            return_exceptions=True,
        )
