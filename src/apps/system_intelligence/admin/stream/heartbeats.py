"""Keeping a chat stream alive: heartbeat events while the model is slow to answer."""

import asyncio

STREAM_HEARTBEAT_SECONDS = 15
_STREAM_END = object()
_STREAM_HEARTBEAT = object()


async def _finished_within(task, timeout) -> bool:
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    return bool(done)


async def _with_heartbeats(event_stream, *, heartbeat_seconds=STREAM_HEARTBEAT_SECONDS):
    """Yield async provider events while keeping idle SSE connections alive."""
    iterator = aiter(event_stream)
    pending_item = None
    try:
        while True:
            pending_item = asyncio.create_task(anext(iterator, _STREAM_END))
            while not await _finished_within(pending_item, heartbeat_seconds):
                yield _STREAM_HEARTBEAT
            # Calling result() preserves provider exceptions (including
            # TimeoutError) instead of confusing them with a heartbeat.
            item = pending_item.result()
            pending_item = None
            if item is _STREAM_END:
                return
            yield item
    finally:
        if pending_item is not None:
            if not pending_item.done():
                pending_item.cancel()
            await asyncio.gather(pending_item, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


async def _awaitable_stream(awaitable):
    """Adapt one awaitable so long setup work can use the heartbeat wrapper."""
    yield await awaitable
