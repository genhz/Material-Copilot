import pytest

from generation.events import RealtimeHub


@pytest.mark.asyncio
async def test_realtime_hub_publishes_to_subscribers() -> None:
    hub = RealtimeHub()
    queue = hub.add_subscriber("generation.job", "job-1")

    await hub.publish(
        "generation.job",
        "job-1",
        {"type": "update", "progress": 0.25},
    )

    assert await queue.get() == {"type": "update", "progress": 0.25}

    hub.remove_subscriber("generation.job", "job-1", queue)
    await hub.publish("generation.job", "job-1", {"type": "update"})
    assert queue.empty()


@pytest.mark.asyncio
async def test_realtime_hub_drops_stale_event_when_queue_is_full() -> None:
    hub = RealtimeHub(queue_size=1)
    queue = hub.add_subscriber("generation.job", "job-2")

    await hub.publish("generation.job", "job-2", {"progress": 0.1})
    await hub.publish("generation.job", "job-2", {"progress": 0.2})

    assert await queue.get() == {"progress": 0.2}
