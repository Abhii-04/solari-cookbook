import asyncio
import time
from typing import Any

from langgraph.config import get_stream_writer


def emit_setup_progress(message: str, **fields: Any) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return

    payload = {
        "type": "repo_setup_progress",
        "message": message,
    }
    payload.update({key: value for key, value in fields.items() if value is not None})
    writer(payload)


async def await_with_progress(
    awaitable,
    message: str,
    *,
    interval_seconds: float = 15,
    **fields: Any,
):
    started = time.monotonic()
    task = asyncio.create_task(awaitable)
    while not task.done():
        await asyncio.sleep(interval_seconds)
        if task.done():
            break
        emit_setup_progress(
            message,
            elapsed_seconds=int(time.monotonic() - started),
            **fields,
        )
    return await task
