from __future__ import annotations

import json

from context import spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers

from .public_ranking_probe import _source_corpus

TARGET_SOURCE = "레이드_델타"
ACTOR_NAME = "아스카 : WILLE"
INTERESTING = {
    "안티 AT 필드",
    "안티 AT 필드 2",
    "섬멸 태세",
    "섬멸 태세 2",
    "섬멸 태세 3",
    "섬멸",
    "섬멸 2",
    "긴급 수복 2",
    "긴급 수복 3",
    "긴급 수복 4",
    "긴급 수복 5",
}


def main() -> None:
    rows = [(members, source) for members, source in _source_corpus() if source == TARGET_SOURCE]
    print("MATCH=" + json.dumps(rows, ensure_ascii=False))
    assert len(rows) == 1, rows

    members, source = rows[0]
    raw = spec.build_squad(list(members))
    compiled = compile_moris_squad(raw)
    blockers = static_score_blockers(compiled)
    print(f"CASE={source} members={members}")
    print("BLOCKERS=" + json.dumps(blockers, ensure_ascii=False))
    assert ACTOR_NAME in members, members
    actor = members.index(ACTOR_NAME)
    sink = SimpleDamageScoreSink(compiled, EnemyStaticProfile(defense=31784.0, duration=180.0))

    for effect in compiled.members[actor].effects:
        if effect.name not in INTERESTING:
            continue
        print("EFFECT=" + repr((
            effect.effect_id,
            effect.name,
            effect.effect_type,
            effect.stat,
            effect.target,
            repr(effect.target_spec),
            tuple((r.raw, r.mode.value, r.event_key, r.interval, r.threshold) for r in effect.triggers),
            tuple(repr(r) for r in effect.condition_rules),
            effect.duration,
            effect.max_stack,
            dict(effect.parameters),
            effect.capability.disposition.value,
            effect.capability.blockers,
            TriggerDispatcher.is_executable_effect(effect),
            sink.supports(effect) if effect.effect_type == "damage" else None,
        )))

    annihilation = next(effect for effect in compiled.members[actor].effects if effect.name == "섬멸")
    remove = next(effect for effect in compiled.members[actor].effects if effect.name == "섬멸 2")
    print("ANNIHILATION_SUPPORTED=" + repr(sink.supports(annihilation)))
    print("REMOVE_EXECUTABLE=" + repr(TriggerDispatcher.is_executable_effect(remove)))
    print("ANNIHILATION_BLOCKERS=" + json.dumps([b for b in blockers if "아스카" in b or "섬멸" in b], ensure_ascii=False))


if __name__ == "__main__":
    main()
