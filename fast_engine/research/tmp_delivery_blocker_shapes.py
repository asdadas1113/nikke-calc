from __future__ import annotations

from collections import Counter, defaultdict

from context import spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    _direct_damage_buff_score_supported,
    static_score_blockers,
)

from .public_ranking_probe import _source_corpus


def _trigger_shape(effect):
    return tuple(
        (
            rule.raw,
            rule.event_key,
            rule.mode.value,
            rule.threshold,
            rule.group,
            rule.interval,
            rule.trigger_count_reducible,
        )
        for rule in effect.triggers
    )


def _effect_shape(effect):
    return (
        effect.effect_type,
        effect.stat,
        repr(effect.target_spec),
        tuple(repr(rule) for rule in effect.condition_rules),
        _trigger_shape(effect),
        effect.duration,
        effect.max_stack,
        tuple(sorted((str(k), repr(v)) for k, v in effect.parameters.items())),
    )


def main() -> None:
    occurrences = defaultdict(set)
    effects = {}
    diagnostics = {}

    for members, source_name in _source_corpus():
        moris_squad = spec.build_squad(list(members))
        compiled = compile_moris_squad(moris_squad)
        blockers = set(static_score_blockers(compiled))
        sink = SimpleDamageScoreSink(
            compiled,
            EnemyStaticProfile(defense=0.0, duration=1.0),
        )

        for effect in compiled.effects:
            owner = compiled.members[effect.actor].name
            label = f"{owner}:{effect.name or effect.stat or '?'}:{effect.stat or '?'}"
            keys = []
            if f"normal_delivery:{label}" in blockers:
                keys.append(("normal_delivery", label))
            if f"skill_state_delivery:{label}" in blockers:
                keys.append(("skill_state_delivery", label))
            if f"skill_damage:{label}" in blockers:
                keys.append(("skill_damage", label))
            if not keys:
                continue

            for kind, _ in keys:
                identity = (kind, owner, effect.name or "", effect.stat or "")
                occurrences[identity].add(source_name)
                effects[identity] = effect
                diagnostics[identity] = {
                    "runtime_direct": is_direct_damage_buff_runtime_supported(effect),
                    "score_direct": _direct_damage_buff_score_supported(compiled, effect)
                    if effect.effect_type == "buff" else None,
                    "damage_sink_supports": sink.supports(effect)
                    if effect.effect_type == "damage" else None,
                    "shape": _effect_shape(effect),
                }

    repeated = [
        (len(teams), identity)
        for identity, teams in occurrences.items()
        if len(teams) >= 2
    ]
    repeated.sort(key=lambda row: (-row[0], row[1]))

    shape_counts = Counter()
    shape_examples = {}
    for count, identity in repeated:
        effect = effects[identity]
        shape = _effect_shape(effect)
        shape_counts[shape] += count
        shape_examples.setdefault(shape, identity)

    print("=== REPEATED DELIVERY BLOCKERS ===")
    for count, identity in repeated:
        effect = effects[identity]
        print(f"BLOCKER teams={count} identity={identity}")
        print(f"  teams={sorted(occurrences[identity])}")
        print(f"  effect_type={effect.effect_type!r} stat={effect.stat!r} value={effect.value!r}")
        print(f"  target={effect.target_spec!r}")
        print(f"  conditions={[repr(rule) for rule in effect.condition_rules]}")
        print(f"  triggers={_trigger_shape(effect)}")
        print(f"  duration={effect.duration!r} max_stack={effect.max_stack!r} max_trigger={effect.max_trigger!r}")
        print(f"  parameters={dict(effect.parameters)!r}")
        print(f"  diagnostics={diagnostics[identity]!r}")

    print("=== REPEATED SHAPE PRESSURE ===")
    for shape, count in shape_counts.most_common(30):
        print(f"SHAPE pressure={count} example={shape_examples[shape]} shape={shape!r}")


if __name__ == "__main__":
    main()
