from __future__ import annotations

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

row = snapshot.SQUADS["스쿼드4"]
squad = spec.build_squad(list(row["members"]))
compiled = compile_moris_squad(squad)
actor = next(i for i, member in enumerate(compiled.members) if member.name == "목단")
print("MORAN_ACTOR", actor, compiled.members[actor].weapon)
for effect in compiled.members[actor].effects:
    if effect.name not in {"정정당당 승부다!", "다 덤벼! 2"}:
        continue
    print("EFFECT", effect.effect_id, effect.name)
    print(" type", effect.effect_type, "stat", effect.stat, "target", effect.target_spec)
    print(" value", effect.value, "duration", effect.duration, "max_stack", effect.max_stack)
    print(" params", dict(effect.parameters))
    print(" capability", effect.capability.disposition.value, tuple(effect.capability.blockers))
    print(" conditions", [
        (rule.mode.value, rule.key, rule.value, rule.raw)
        for rule in effect.condition_rules
    ])
    print(" triggers", [
        (rule.mode.value, rule.event_key, rule.threshold, rule.trigger_count_reducible, rule.raw)
        for rule in effect.triggers
    ])
print("BLOCKERS", static_score_blockers(compiled))
