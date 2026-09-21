"""In-process pub/sub hub for realtime WebSocket events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class RealtimeHub:
    """Fan out channel events to WebSocket subscribers."""

    def __init__(self, queue_size: int = 32):
        self._queue_size = queue_size
        self._subscribers: dict[
            tuple[str, str], set[asyncio.Queue[dict[str, Any]]]
        ] = defaultdict(set)

    def add_subscriber(self, channel: str, resource_id: str) -> asyncio.Queue:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=self._queue_size
        )
        self._subscribers[(channel, resource_id)].add(queue)
        return queue

    def remove_subscriber(
        self,
        channel: str,
        resource_id: str,
        queue: asyncio.Queue,
    ) -> None:
        key = (channel, resource_id)
        subscribers = self._subscribers.get(key)
        if not subscribers:
            return

        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(key, None)

    async def publish(
        self,
        channel: str,
        resource_id: str,
        payload: dict[str, Any],
    ) -> None:
        subscribers = list(self._subscribers.get((channel, resource_id), ()))
        for queue in subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)
