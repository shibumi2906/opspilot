"""Keep blocking transport admission occupied until the actual thread finishes."""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Any

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="connector-transport")
_admission = BoundedSemaphore(4)


async def bounded[T](function: Callable[..., T], *args: Any, budget: float) -> T:
    if not _admission.acquire(blocking=False):
        raise TimeoutError()
    try:
        future = _pool.submit(function, *args)
    except BaseException:
        _admission.release()
        raise
    future.add_done_callback(lambda done: _admission.release())
    return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), budget)
