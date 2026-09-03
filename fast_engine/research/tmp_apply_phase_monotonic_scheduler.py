from __future__ import annotations

from pathlib import Path


def apply() -> None:
    path = Path("fast_engine/engine/scheduler.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from typing import Any\n",
        "from typing import Any\n\nfrom .frame_lattice import moris_next_tick\n",
        1,
    )
    text = text.replace(
        '''    __slots__ = ("_heap", "_sequence", "now")\n\n    def __init__(self) -> None:\n        self._heap: list[ScheduledEvent] = []\n        self._sequence = 0\n        self.now = 0.0\n''',
        '''    __slots__ = ("_heap", "_sequence", "now", "_phase")\n\n    def __init__(self) -> None:\n        self._heap: list[ScheduledEvent] = []\n        self._sequence = 0\n        self.now = 0.0\n        self._phase = -10**9\n''',
        1,
    )
    old = '''        if time < self.now:\n            raise ValueError(f"cannot schedule event in the past: now={self.now}, time={time}")\n        phase = _EVENT_PHASE.get(kind, 100)\n        # duration_bullets expires only after the consuming shot's damage and\n'''
    new = '''        if time < self.now:\n            raise ValueError(f"cannot schedule event in the past: now={self.now}, time={time}")\n        phase = _EVENT_PHASE.get(kind, 100)\n        # Moris executes one outer frame in semantic phase order. If work in a\n        # later phase (e.g. weapon/trigger) creates an event for a phase that has\n        # already passed in this same frame (e.g. burst), that event cannot run\n        # by rewinding the frame. Observe it on the next Moris outer-loop tick.\n        if float(time) == self.now and phase < self._phase:\n            time = moris_next_tick(self.now, horizon=self.now + 1.0)\n        # duration_bullets expires only after the consuming shot's damage and\n'''
    assert old in text, "schedule block not found"
    text = text.replace(old, new, 1)
    old = '''    def pop(self) -> ScheduledEvent:\n        event = heapq.heappop(self._heap)\n        self.now = event.time\n        return event\n'''
    new = '''    def pop(self) -> ScheduledEvent:\n        event = heapq.heappop(self._heap)\n        if event.time != self.now:\n            self._phase = -10**9\n        self.now = event.time\n        self._phase = event.phase\n        return event\n'''
    assert old in text, "pop block not found"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    apply()
