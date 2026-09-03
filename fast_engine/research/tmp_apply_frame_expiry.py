from __future__ import annotations

from pathlib import Path


def apply() -> None:
    path = Path("fast_engine/engine/effects.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from .scheduler import EventKind, EventScheduler, ScheduledEvent\n",
        "from .frame_lattice import moris_observed_tick\n"
        "from .scheduler import EventKind, EventScheduler, ScheduledEvent\n",
        1,
    )
    old = '''        duration = effect.duration
        expires = inf if duration is None or duration == -1 else now + max(0.0, duration)
        generation = self._next_generation()
'''
    new = '''        duration = effect.duration
        if duration is None or duration == -1:
            expires = inf
        elif float(duration) > 0.0:
            # Moris stores the continuous deadline, but finite effects are only
            # removed by BuffManager.tick() on the first 60 Hz outer-loop frame
            # satisfying t >= deadline. Fast has no outer frame loop, so use the
            # frame at which Moris can actually observe the expiry.
            deadline = now + float(duration)
            expires = moris_observed_tick(deadline, horizon=deadline + 1.0)
        else:
            # Zero-duration effects are activated after the current Moris
            # BuffManager.tick and have separate same-frame/next-frame semantics.
            # Leave them untouched in this narrow A/B experiment.
            expires = now
        generation = self._next_generation()
'''
    assert old in text, "finite expiry block not found"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


if __name__ == "__main__":
    apply()
