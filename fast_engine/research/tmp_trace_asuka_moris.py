from __future__ import annotations

from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec

NAMES = ["미란다", "아스카 : WILLE", "브리드 : 사일런트 트랙", "헬름", "루주"]
CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}
ENEMY = dict(DEFAULT_ENEMY)
ENEMY.update({"def": 55000.0, "code": "작열", "core_px": 10.0})
ASUKA = "아스카 : WILLE"


def anti_stack(manager: BuffManager) -> int:
    return int(max(
        (
            active.stack
            for active in manager._active
            if active.caster == ASUKA and active.effect.get("name") == "안티 AT 필드"
        ),
        default=0,
    ))


def main() -> None:
    squad = spec.build_squad(NAMES)
    original_notify = BuffManager.notify
    state_ends: list[tuple[float, int]] = []
    stack_changes: list[tuple[float, int, str]] = []
    hit_times: list[float] = []
    last_stack = [0]

    def notify(manager, event, t, caster, **ctx):
        if caster == ASUKA and event == "event:state_end:섬멸 태세":
            state_ends.append((float(t), anti_stack(manager)))
        out = original_notify(manager, event, t, caster, **ctx)
        if caster == ASUKA and event == "hit_count":
            hit_times.append(float(t))
            stack = anti_stack(manager)
            if stack != last_stack[0]:
                stack_changes.append((float(t), stack, event))
                last_stack[0] = stack
        return out

    with patch.object(BuffManager, "notify", new=notify):
        result = simulate(
            squad,
            config=spec.build_config(squad, CONFIG),
            enemy=dict(ENEMY),
            seed=0,
            verbose=False,
        )

    print(f"MORIS_TOTAL={float(result.squad_total):.9f}")
    print("MORIS_STATE_ENDS=" + repr(state_ends))
    print("MORIS_STACK_CHANGES_135_PLUS=" + repr([row for row in stack_changes if row[0] >= 135.0]))
    print("MORIS_HITS_135_PLUS=" + repr([t for t in hit_times if t >= 135.0]))
    for i, (end, stack) in enumerate(state_ends):
        start = state_ends[i - 1][0] if i else 0.0
        shots = sum(start < t <= end for t in hit_times)
        print(f"MORIS_WINDOW index={i} start={start:.9f} end={end:.9f} shots={shots} stack={stack}")


if __name__ == "__main__":
    main()
