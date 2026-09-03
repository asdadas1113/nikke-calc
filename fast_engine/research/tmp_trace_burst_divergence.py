from __future__ import annotations

from unittest.mock import patch

from calculator.buff_manager import BuffManager
from fast_engine.engine.burst import BurstMachine
from fast_engine.research import tmp_validate_asuka_mg_v2 as validation


def main() -> None:
    old_handle = BurstMachine.handle
    old_cast = BurstMachine._cast_signals
    old_notify = BuffManager.notify

    fast_events: list[tuple] = []
    fast_casts: list[tuple] = []
    moris_events: list[tuple] = []

    def traced_handle(machine, event, scheduler, **kwargs):
        before = (machine.phase, machine.cycle_count)
        out = old_handle(machine, event, scheduler, **kwargs)
        after = (machine.phase, machine.cycle_count)
        if 100.0 <= float(event.time) <= 140.0:
            token = event.payload
            fast_events.append((
                float(event.time),
                event.kind.name,
                getattr(token, "stage", None),
                before,
                after,
                machine.full_burst_end_at,
            ))
        return out

    def traced_cast(machine, actor, stage, now):
        if 100.0 <= float(now) <= 140.0:
            fast_casts.append((
                float(now),
                machine.squad.members[actor].name,
                str(stage),
                int(machine.cycle_count),
                tuple(machine.ready_at),
                tuple(machine.gauge_ready_at),
            ))
        return old_cast(machine, actor, stage, now)

    def traced_notify(manager, event, t, caster, **ctx):
        if 100.0 <= float(t) <= 140.0:
            keep = False
            if event == "burst_cast":
                keep = True
            elif event in {"full_burst_start", "full_burst_end"}:
                # These are broadcast to every owner; one row is enough.
                keep = caster == validation.NAMES[0]
            elif event.startswith("burst_enter:"):
                keep = caster == validation.NAMES[0]
            if keep:
                moris_events.append((float(t), event, caster))
        return old_notify(manager, event, t, caster, **ctx)

    try:
        with (
            patch.object(BurstMachine, "handle", new=traced_handle),
            patch.object(BurstMachine, "_cast_signals", new=traced_cast),
            patch.object(BuffManager, "notify", new=traced_notify),
        ):
            try:
                validation.main()
            except AssertionError as exc:
                print("EXPECTED_VALIDATION_FAILURE=", exc)
    finally:
        print("FAST_BURST_EVENTS_100_140=")
        for row in fast_events:
            print(row)
        print("FAST_CASTS_100_140=")
        for row in fast_casts:
            print(row)
        print("MORIS_BURST_EVENTS_100_140=")
        for row in moris_events:
            print(row)


if __name__ == "__main__":
    main()
