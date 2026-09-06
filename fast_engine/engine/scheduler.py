from __future__ import annotations

import heapq
from contextvars import ContextVar
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
    BURST_END_FINALIZE = 15
    DAMAGE_TICK = 19
    STATE_EXPIRE = 20
    STATE_END_NOTIFY = 21
    PERIODIC_TICK = 30
    RELOAD_DONE = 40
    PRE_SHOT_BOUNDARY = 45
    WEAPON_BOUNDARY = 50
    TRIGGER_BOUNDARY = 60
    CUSTOM = 100


# Moris frame order is buff-manager tick -> burst controller -> weapon actors.
# Inside BuffManager.tick, periodic damage is processed before buff expiry and
# every:Ns skill ticks. Only equal-time events use this phase key; continuous
# timestamps remain untouched. Same-phase non-weapon events preserve insertion
# order; phase-30 weapon work is additionally ordered by roster actor.
_EVENT_PHASE: dict[EventKind, int] = {
    EventKind.DAMAGE_TICK: -10,
    EventKind.STATE_EXPIRE: 0,
    EventKind.STATE_END_NOTIFY: 5,
    EventKind.PERIODIC_TICK: 10,
    EventKind.BURST_READY: 20,
    EventKind.BURST_ACTIVATE: 20,
    EventKind.BURST_REENTER: 20,
    EventKind.FULL_BURST_START: 20,
    EventKind.FULL_BURST_END: 20,
    EventKind.BURST_END_FINALIZE: 20,
    EventKind.RELOAD_DONE: 30,
    EventKind.PRE_SHOT_BOUNDARY: 30,
    EventKind.WEAPON_BOUNDARY: 30,
    EventKind.TRIGGER_BOUNDARY: 30,
    EventKind.CUSTOM: 100,
}


# Static score blocks are compressed by actor rather than materialized as one
# global 60 Hz/per-shot stream. While one phase-30 weapon actor is being handled,
# an inclusive score consume at the same timestamp may therefore advance only
# through that actor. ContextVar keeps this sparse transaction local to the
# current synchronous execution context and leaves standalone cursor use intact.
_SCORE_ACTOR_TRANSACTION: ContextVar[tuple[float, int] | None] = ContextVar(
    "fast_score_actor_transaction",
    default=None,
)
_SCORE_ACTOR_EPS = 1e-9


def score_actor_cutoff(time: float) -> int | None:
    """Return the current Moris weapon-actor cutoff for exact ``time`` scoring."""

    row = _SCORE_ACTOR_TRANSACTION.get()
    if row is None:
        return None
    txn_time, actor = row
    if abs(float(time) - txn_time) > _SCORE_ACTOR_EPS:
        return None
    return actor


@dataclass(order=True, slots=True)
class ScheduledEvent:
    sort_key: tuple[float, int, int, int, int] = field(init=False, repr=False)
    time: float = field(compare=False)
    phase: int = field(compare=False)
    sequence: int = field(compare=False)
    kind: EventKind = field(compare=False)
    actor: int = field(compare=False, default=-1)
    payload: Any = field(compare=False, default=None)

    def __post_init__(self) -> None:
        # Moris runs weapon actors in roster order inside one frame. Preserve the
        # historical stable sequence everywhere else, but make equal-time phase-30
        # work sparse-actor ordered so dynamic and static boundaries share one
        # transaction without introducing a frame loop.
        actor_order = self.actor if self.phase == 30 and self.actor >= 0 else -1
        # A pre-shot boundary must run after earlier roster actors at the same
        # timestamp, but before any ordinary boundary belonging to its own actor.
        actor_subphase = -1 if self.kind is EventKind.PRE_SHOT_BOUNDARY else 0
        self.sort_key = (
            float(self.time),
            int(self.phase),
            int(actor_order),
            int(actor_subphase),
            int(self.sequence),
        )


class EventScheduler:
    """Continuous-time stable priority queue.

    There is deliberately no 1/60 s loop. Equal-time events follow Moris'
    semantic frame phases (DoT -> expiry -> periodic -> burst -> weapon). Within
    the weapon phase they follow roster actor order and then insertion order;
    other phases remain insertion-stable. This prevents activation history from
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
        phase = _EVENT_PHASE.get(kind, 100)
        # duration_bullets expires only after the consuming shot's damage and
        # hit notifications. Reuse STATE_EXPIRE handling, but place tagged
        # expiry tokens after all phase-30 weapon/trigger work at the same time.
        if kind is EventKind.STATE_EXPIRE and getattr(payload, "post_shot", False):
            phase = 40
        event = ScheduledEvent(
            float(time),
            phase,
            self._sequence,
            kind,
            actor,
            payload,
        )
        self._sequence += 1
        heapq.heappush(self._heap, event)

    def peek_time(self) -> float | None:
        next_time = self._heap[0].time if self._heap else None
        row = _SCORE_ACTOR_TRANSACTION.get()
        if row is not None:
            txn_time, _actor = row
            if next_time is None or next_time > txn_time + _SCORE_ACTOR_EPS:
                # BurstRuntime calls peek_time() before its end-of-timestamp score
                # drain. Clearing here lets that final inclusive consume pick up
                # actors after the last meaningful phase-30 boundary.
                _SCORE_ACTOR_TRANSACTION.set(None)
        return next_time

    def pop(self) -> ScheduledEvent:
        event = heapq.heappop(self._heap)
        self.now = event.time
        if event.phase == 30 and event.actor >= 0:
            _SCORE_ACTOR_TRANSACTION.set((float(event.time), int(event.actor)))
        else:
            _SCORE_ACTOR_TRANSACTION.set(None)
        return event

    def clear(self) -> None:
        self._heap.clear()
        _SCORE_ACTOR_TRANSACTION.set(None)
