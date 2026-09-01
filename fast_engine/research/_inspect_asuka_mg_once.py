from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
import fast_engine.engine.score as score

names = [
    "리틀 머메이드",
    "델타 : 닌자 시프",
    "크라운",
    "아스카 : WILLE",
    "라피 : 레드 후드",
]
squad = compile_moris_squad(build_squad(names))
consumer = next(
    e for e in squad.effects
    if e.actor == 3 and e.name == "긴급 수복 2" and e.stat == "mg_warmup_speed_pct"
)
print("CONSUMER", consumer)
print("EXECUTABLE", TriggerDispatcher.is_executable_effect(consumer))
print("POSSIBLE_TARGETS", score._possible_ally_targets(squad, consumer))
print("DYNAMIC_SUPPORTED", score._is_dynamic_mg_warmup_score_supported(squad, consumer))

print("=== PROVIDERS named 섬멸 태세 ===")
for effect in squad.effects:
    if effect.actor == consumer.actor and effect.name == "섬멸 태세":
        print(effect)

print("=== EFFECTS referencing 섬멸 태세 in params/triggers/conditions ===")
for effect in squad.effects:
    blob = " ".join([
        effect.name or "",
        effect.stat or "",
        repr(effect.parameters),
        repr(effect.triggers),
        repr(effect.condition_rules),
    ])
    if "섬멸 태세" in blob:
        print(effect)

print("=== ASUKA effects summary ===")
for effect in squad.members[consumer.actor].effects:
    print(
        effect.effect_id,
        effect.name,
        effect.effect_type,
        effect.stat,
        effect.duration,
        effect.parameters,
        tuple(rule.raw for rule in effect.triggers),
        effect.capability.disposition.value,
        effect.capability.blockers,
    )
