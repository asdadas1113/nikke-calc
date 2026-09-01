from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class EventKind(IntEnum):
    """Generic runtime boundaries. Character names never belong here."""

    BURST_READY = 10
    BURST_ACTIVATE = 11
    BURST_REENTER = 12
    FULL_BURST_START = 13
    FULL_BURST_END = 14
    STATE_EXPIRE = 20
    PERIODIC_TICK = 30
    RELOAD_DONE = 40
    WEAPON_BOUNDARY = 50
    TRIGGER_BOUNDARY = 60
    CUSTOM = 100


# Moris frame order is buff-manager tick -> burst controller -> weapon actors.
# Only equal-time events use this phase key; continuous timestamps remain untouched.
# Same-phase events still preserve insertion order through sequence.
_EVENT_PHASE: dict[EventKind, int] = {
    EventKind.STATE_EXPIRE: 0,
    EventKind.PERIODIC_TICK: 10,
    EventKind.BURST_READY: 20,
    EventKind.BURST_ACTIVATE: 20,
    EventKind.BURST_REENTER: 20,
    EventKind.FULL_BURST_START: 20,
    EventKind.FULL_BURST_END: 20,
    EventKind.RELOAD_DONE: 30,
    EventKind.WEAPON_BOUNDARY: 30,
    EventKind.TRIGGER_BOUNDARY: 30,
    EventKind.CUSTOM: 100,
}


@dataclass(order=True, slots=True)
class ScheduledEvent:
    time: float
    phase: int
    sequence: int
    kind: EventKind = field(compare=False)
    actor: int = field(compare=False, default=-1)
    payload: Any = field(compare=False, default=None)


class EventScheduler:
    """Continuous-time stable priority queue.

    There is deliberately no 1/60 s loop. Equal-time events follow Moris'
    semantic frame phases (expiry -> periodic -> burst -> weapon), then preserve
    insertion order inside the same phase. This prevents activation-history from
    accidentally deciding combat semantics.
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
        event = ScheduledEvent(
            float(time),
            _EVENT_PHASE.get(kind, 100),
            self._sequence,
            kind,
            actor,
            payload,
        )
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
