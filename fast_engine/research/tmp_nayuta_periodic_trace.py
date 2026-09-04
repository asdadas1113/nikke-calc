from __future__ import annotations

import json
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec

from .public_ranking_probe import _source_corpus

TARGET_SOURCE = "레이드_델타"
ACTOR_NAME = "아스카 : WILLE"
STATE_NAME = "안티 AT 필드"


def _enemy_stack(manager: BuffManager) -> int:
    return max(
        (
            int(ab.stack)
            for ab in manager._active
            if ab.caster == ACTOR_NAME
            and ab.effect.get("name") == STATE_NAME
            and "__enemy__" in (ab.target_chars or [])
        ),
        default=0,
    )


def main() -> None:
    rows = [(members, source) for members, source in _source_corpus() if source == TARGET_SOURCE]
    assert len(rows) == 1, rows
    members, source = rows[0]
    raw = spec.build_squad(list(members))

    original_activate = BuffManager._activate
    order: list[tuple[str, str, float, int]] = []

    def activate(manager, eff, caster, t, *args, **kwargs):
        name = eff.get("name")
        if caster == ACTOR_NAME and name in {"섬멸", "섬멸 2"}:
            order.append(("before", str(name), float(t), _enemy_stack(manager)))
            out = original_activate(manager, eff, caster, t, *args, **kwargs)
            order.append(("after", str(name), float(t), _enemy_stack(manager)))
            return out
        return original_activate(manager, eff, caster, t, *args, **kwargs)

    config = spec.build_config(raw, {
        "duration": 25.0,
        "first_burst_time": 3.0,
        "rng_mode": "expected",
    })
    with patch.object(BuffManager, "_activate", new=activate):
        result = simulate(
            raw,
            config=config,
            enemy=dict(DEFAULT_ENEMY),
            seed=42,
            verbose=True,
        )

    hits = [
        (float(hit.t), int(hit.damage), hit.hit_tag, hit.skill_name)
        for hit in result.hits
        if hit.caster == ACTOR_NAME and hit.skill_name == "섬멸"
    ]
    burst = [] if result.log is None else [
        (float(row.t), row.event, row.caster)
        for row in result.log.burst_log
        if row.caster == ACTOR_NAME or row.event.startswith("full_burst")
    ]
    field_events = [] if result.log is None else [
        (float(row.t), row.kind, row.name, row.caster, row.target, row.stack, row.max_stack)
        for row in result.log.buff_events
        if row.name in {STATE_NAME, "섬멸 태세"}
    ]

    print(f"SOURCE={source} MEMBERS={members}")
    print("BURST=" + repr(burst))
    print("ORDER=" + repr(order))
    print("ANNIHILATION_HITS=" + repr(hits))
    print("FIELD_EVENTS=" + repr(field_events))

    assert order, "Asuka WILLE did not cast/expire annihilation stance"
    first_t = order[0][2]
    first = [row for row in order if abs(row[2] - first_t) < 1e-9]
    print("FIRST_STATE_END_ORDER=" + repr(first))
    first_hit = next((row for row in hits if abs(row[0] - first_t) < 1e-9), None)
    print("FIRST_STATE_END_HIT=" + repr(first_hit))

    # Moris semantic contract: damage reads the accumulated enemy stack, then
    # the immediately following remove_named_buff clears the named state.
    assert first[0][0:2] == ("before", "섬멸"), first
    assert first[0][3] > 0, first
    assert first[1][0:2] == ("after", "섬멸"), first
    assert first[1][3] == first[0][3], first
    assert first[2][0:2] == ("before", "섬멸 2"), first
    assert first[2][3] == first[0][3], first
    assert first[3][0:2] == ("after", "섬멸 2"), first
    assert first[3][3] == 0, first
    assert first_hit is not None, (first, hits)


if __name__ == "__main__":
    main()
