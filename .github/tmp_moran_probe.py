from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers

MORAN_TEAMS = (
    "스쿼드4",
    "레이드_이브레이븐",
    "레이드_아니스서머메이든",
    "레이드_브리드디젤",
    "레이드_트리나홍련",
)

print("=== MORAN PUBLIC BLOCKERS ===", flush=True)
for name in MORAN_TEAMS:
    case = snapshot.SQUADS[name]
    squad = spec.build_squad(list(case["members"]))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    print(name, "members=", tuple(case["members"]), flush=True)
    print(" blockers=", blockers, flush=True)
    assert not any(b.startswith("weapon_change:목단:") for b in blockers), (name, blockers)

print("=== MORAN 180S PRODUCTION SCORE ===", flush=True)
audit_name = "스쿼드4"
case = snapshot.SQUADS[audit_name]
squad = spec.build_squad(list(case["members"]))
compiled = compile_moris_squad(squad)
assert static_score_blockers(compiled) == ()
cfg = spec.build_config(squad, {
    "duration": 180.0,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
})
policy = compile_burst_policy(squad, compiled, cfg)
enemy = EnemyStaticProfile(defense=31784.0, duration=180.0, core_px=0.0)
t0 = perf_counter()
score = score_static_squad(compiled, policy, enemy)
elapsed = perf_counter() - t0
print("MORAN_180S_AUDIT", audit_name, flush=True)
print(" squad_total", score.squad_total, flush=True)
print(" char_total", score.char_total, flush=True)
print(" events_processed", score.events_processed, flush=True)
print(" unsupported", score.unsupported, flush=True)
print(" elapsed_seconds", elapsed, flush=True)
assert score.unsupported == ()
assert score.squad_total > 0.0

print("=== CANONICAL PUBLIC FRONTIER ===", flush=True)
source_cases = []
unique = {}
for name, case in snapshot.SQUADS.items():
    if str(name).startswith("지그_"):
        continue
    members = tuple(case.get("members") or ())
    if len(members) != 5:
        continue
    if any(str(member).startswith("test_") for member in members):
        continue
    source_cases.append((name, members))
    unique.setdefault(members, name)

family_counts = Counter()
certified = []
gaps = []
for members, name in unique.items():
    squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    if blockers:
        gaps.append((name, members, blockers))
        family_counts.update(b.split(":", 1)[0] for b in blockers)
    else:
        certified.append((name, members))

print("SOURCE_CASES", len(source_cases), flush=True)
print("UNIQUE_MEMBERSHIPS", len(unique), flush=True)
print("CERTIFIED_COUNT", len(certified), flush=True)
print("GAP_COUNT", len(gaps), flush=True)
print("CERTIFIED_NAMES", tuple(name for name, _ in certified), flush=True)
print("BLOCKER_FAMILIES", dict(sorted(family_counts.items())), flush=True)

assert len(source_cases) == 24
assert len(unique) == 23
assert len(certified) == 6
assert len(gaps) == 17
assert family_counts == Counter({
    "normal_delivery": 46,
    "normal_state": 16,
    "skill_damage": 25,
    "skill_state_delivery": 48,
    "weapon_change": 7,
    "cadence": 53,
    "control": 4,
    "periodic_grid": 1,
})
