"""Thread-safe priority scheduling for inventory follow-up jobs."""

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from queue import PriorityQueue
from threading import Lock
from typing import List, Optional
from uuid import uuid4


URGENT_PRIORITY = 1
HIGH_PRIORITY = 2
NORMAL_PRIORITY = 3


def priority_for_stock(stock_quantity: int, reorder_threshold: int) -> int:
    if stock_quantity < 0 or reorder_threshold < 0:
        raise ValueError("stock quantity and reorder threshold must be non-negative")
    if stock_quantity == 0:
        return URGENT_PRIORITY
    if stock_quantity < reorder_threshold:
        return HIGH_PRIORITY
    return NORMAL_PRIORITY


@dataclass(frozen=True)
class ScheduledJob:
    id: str
    priority: int
    job_type: str
    product_id: Optional[int]
    description: str
    queued_at: datetime


class PriorityScheduler:
    """Stable, thread-safe priority queue (lower numeric values run first)."""

    def __init__(self) -> None:
        self._queue = PriorityQueue()
        self._sequence = count()
        self._lock = Lock()

    def enqueue(
        self,
        priority: int,
        job_type: str,
        product_id: Optional[int] = None,
        description: str = "",
    ) -> ScheduledJob:
        if priority not in (URGENT_PRIORITY, HIGH_PRIORITY, NORMAL_PRIORITY):
            raise ValueError("priority must be 1 (urgent), 2 (high), or 3 (normal)")
        job = ScheduledJob(
            id=uuid4().hex,
            priority=priority,
            job_type=job_type,
            product_id=product_id,
            description=description,
            queued_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._queue.put((priority, next(self._sequence), job))
        return job

    def snapshot(self) -> List[ScheduledJob]:
        with self._lock:
            return [entry[2] for entry in sorted(self._queue.queue)]

    def pop_next(self) -> Optional[ScheduledJob]:
        with self._lock:
            if self._queue.empty():
                return None
            return self._queue.get_nowait()[2]

    def __len__(self) -> int:
        with self._lock:
            return self._queue.qsize()


priority_scheduler = PriorityScheduler()