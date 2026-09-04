from __future__ import annotations

import json
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import static_score_blockers

from .public_ranking_probe import _source_corpus

NAME = "나유타"
DURATION = 100.0
CONFIG = {"duration": DURATION, "first_burst_time": 3.0, "rng_mode": "expected"}


def _stack(manager: BuffManager) -> int:
    return max(
        (
            int(ab.stack)
            for ab in manager._active
            if ab.caster == NAME and ab.effect.get("name") == "기억 흡수"
        ),
        default=0,
    )


def main() -> None:
    cases = [(members, source) for members, source in _source_corpus() if NAME in members]
    print("NAYUTA_CASES=" + json.dumps(cases, ensure_ascii=False))
    assert cases, "no Nayuta public case"

    for members, source in cases:
        raw = spec.build_squad(list(members))
        compiled = compile_moris_squad(raw)
        print(f"CASE {source} members={members}")
        print("BLOCKERS=" + json.dumps([b for b in static_score_blockers(compiled) if NAME in b], ensure_ascii=False))
        for effect in compiled.members[members.index(NAME)].effects:
            if effect.name in {"기억 흡수", "무상", "무상 2", "무상 3", "위선", "위선 2", "위선 3", "위선 4"}:
                print("EFFECT=" + repr((
                    effect.effect_id, effect.name, effect.effect_type, effect.stat,
                    tuple((r.raw, r.mode.value, r.event_key, r.interval, r.threshold) for r in effect.triggers),
                    tuple(repr(r) for r in effect.condition_rules), effect.duration, effect.max_stack,
                    effect.capability.disposition.value, effect.capability.blockers,
                    TriggerDispatcher.is_executable_effect(effect),
                )))

    members, source = cases[0]
    raw = spec.build_squad(list(members))
    original_activate = BuffManager._activate
    original_notify = BuffManager.notify
    activations: list[tuple[float, int, int]] = []
    named_events: list[tuple[float, str, int]] = []

    def activate(manager, eff, caster, t, *args, **kwargs):
        before = _stack(manager) if caster == NAME and eff.get("name") == "기억 흡수" else None
        out = original_activate(manager, eff, caster, t, *args, **kwargs)
        if before is not None:
            after = _stack(manager)
            if after != before:
                activations.append((float(t), int(before), int(after)))
        return out

    def notify(manager, event, t, caster, **ctx):
        if caster == NAME and event == "기억 흡수":
            named_events.append((float(t), str(event), _stack(manager)))
        return original_notify(manager, event, t, caster, **ctx)

    with patch.object(BuffManager, "_activate", new=activate), patch.object(BuffManager, "notify", new=notify):
        simulate(
            raw,
            config=spec.build_config(raw, dict(CONFIG)),
            enemy=dict(DEFAULT_ENEMY),
            seed=42,
            verbose=False,
        )

    print(f"TRACE_SOURCE={source}")
    print("MORIS_MEMORY_ABSORB=" + repr(activations))
    print("MORIS_MEMORY_EVENTS=" + repr(named_events))
    assert len(activations) == 30, activations
    assert [row[2] for row in activations] == list(range(1, 31)), activations
    assert len(named_events) == 30, named_events
    assert all(abs(t - 3.0 * (i + 1)) <= 1.0 / 60.0 + 1e-9 for i, (t, _, _) in enumerate(named_events)), named_events
    assert [stack for _, _, stack in named_events] == list(range(1, 31)), named_events


if __name__ == "__main__":
    main()
