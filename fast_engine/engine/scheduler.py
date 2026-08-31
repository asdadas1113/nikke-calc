from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class EventKind(IntEnum):
    """Generic runtime boundaries. Character names never belong here."""

    BURST_READY = 10
    BURST_ACTIVATE = 11
    STATE_EXPIRE = 20
    PERIODIC_TICK = 30
    RELOAD_DONE = 40
    WEAPON_BOUNDARY = 50
    TRIGGER_BOUNDARY = 60
    CUSTOM = 100


@dataclass(order=True, slots=True)
class ScheduledEvent:
    time: float
    sequence: int
    kind: EventKind = field(compare=False)
    actor: int = field(compare=False, default=-1)
    payload: Any = field(compare=False, default=None)


class EventScheduler:
    """Continuous-time stable priority queue.

    There is deliberately no 1/60 s loop. Equal-time events preserve insertion
    order so compiler/runtime decisions remain deterministic.
    """

    __slots__ = ("_heap", "_sequence", "now")

    def __init__(self) -> None:
        self._heap: list[ScheduledEvent] = []
        self._sequence = 0
        self.now = 0.0

    def __bool__(self) -> bool:
        return bool(self._heap)

    def __len__(self) -> int:
        return len(self._heap)

    def schedule(self, time: float, kind: EventKind, actor: int = -1, payload: Any = None) -> None:
        if time < self.now:
            raise ValueError(f"cannot schedule event in the past: now={self.now}, time={time}")
        event = ScheduledEvent(float(time), self._sequence, kind, actor, payload)
        self._sequence += 1
        heapq.heappush(self._heap, event)

    def peek_time(self) -> float | None:
        return self._heap[0].time if self._heap else None

    def pop(self) -> ScheduledEvent:
        event = heapq.heappop(self._heap)
        self.now = event.time
        return event

    def clear(self) -> None:
        self._heap.clear()
