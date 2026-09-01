from pathlib import Path

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
    print(
        "TARGET",
        actor,
        member.name,
        "mode=", member.weapon.get("fire_mode"),
        "rapid_safe=", score._rapid_actor_score_safe(squad, actor),
    )

for path in ("calculator/buff_manager.py", "calculator/timeline.py", "fast_engine/engine/dispatcher.py", "fast_engine/engine/effects.py"):
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    print(f"=== {path} state_end contexts ===")
    found = False
    for idx, line in enumerate(lines):
        if "state_end" not in line:
            continue
        found = True
        lo = max(0, idx - 8)
        hi = min(len(lines), idx + 12)
        print(f"--- lines {lo + 1}-{hi} ---")
        for j in range(lo, hi):
            print(f"{j + 1:05d}: {lines[j]}")
    if not found:
        print("<none>")
