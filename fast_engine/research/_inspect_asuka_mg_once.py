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
effect = next(
    e for e in squad.effects
    if e.actor == 3 and e.name == "긴급 수복 2" and e.stat == "mg_warmup_speed_pct"
)
print("EFFECT", effect)
print("EXECUTABLE", TriggerDispatcher.is_executable_effect(effect))
print("POSSIBLE_TARGETS", score._possible_ally_targets(squad, effect))
print("DYNAMIC_SUPPORTED", score._is_dynamic_mg_warmup_score_supported(squad, effect))
unsafe_events = frozenset({
    "last_bullet_fire", "last_bullet", "on_attack", "event:full_reload",
    "full_reload", "event:cover",
})
for actor in score._possible_ally_targets(squad, effect):
    member = squad.members[actor]
    weapon_change = [
        e.name for e in squad.effects
        if e.effect_type == "weapon_change" and actor in score._possible_ally_targets(squad, e)
    ]
    global_body = any(
        TriggerDispatcher.is_executable_effect(e)
        and any(rule.event_key == "squad_body_hit" for rule in e.triggers)
        for e in squad.effects
    )
    print(
        "TARGET",
        actor,
        member.name,
        "mode=", member.weapon.get("fire_mode"),
        "control=", member.weapon.get("control"),
        "clip=", member.weapon.get("is_clip"),
        "cover_delay=", member.weapon.get("cover_during_delay"),
        "rapid_safe=", score._rapid_actor_score_safe(squad, actor),
        "core=", score._actor_has_executable_core_count(squad, actor),
        "unsafe_event=", score._actor_has_executable_event(squad, actor, unsafe_events),
        "unhandled_count=", score._actor_has_unhandled_count_event(squad, actor, frozenset({"hit_count", "pellet_hit"})),
        "weapon_change=", weapon_change,
        "global_body=", global_body,
    )
