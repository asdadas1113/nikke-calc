from __future__ import annotations

from bisect import bisect_left, bisect_right
from functools import lru_cache
from math import ceil

_MORIS_DT = 1.0 / 60.0


@lru_cache(maxsize=32)
def _repeated_add_ticks(horizon_seconds: int) -> tuple[float, ...]:
    """Return Moris outer-loop timestamps from repeated ``t += 1/60``."""
    limit = max(1, int(horizon_seconds))
    ticks: list[float] = []
    t = 0.0
    while t <= float(limit) + _MORIS_DT:
        ticks.append(t)
        t += _MORIS_DT
    return tuple(ticks)


def _ticks_for(deadline: float, horizon: float) -> tuple[float, ...]:
    limit = max(float(deadline), float(horizon), 0.0)
    return _repeated_add_ticks(int(ceil(limit)) + 2)


def moris_observed_tick(
    deadline: float, *, horizon: float, epsilon: float = 0.0
) -> float:
    """First repeated-add Moris tick satisfying ``t >= deadline - epsilon``."""
    value = float(deadline)
    ticks = _ticks_for(value, horizon)
    index = bisect_left(ticks, value - float(epsilon))
    return ticks[index] if index < len(ticks) else value


def moris_next_tick(after: float, *, horizon: float) -> float:
    """First repeated-add Moris tick strictly after ``after``."""
    value = float(after)
    ticks = _ticks_for(value, horizon)
    index = bisect_right(ticks, value)
    return ticks[index] if index < len(ticks) else value + _MORIS_DT
