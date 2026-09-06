from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

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

print("=== MORAN PUBLIC BLOCKERS ===")
certifiable_moran = []
for name in MORAN_TEAMS:
    case = snapshot.SQUADS[name]
    squad = spec.build_squad(list(case["members"]))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    print(name, "members=", tuple(case["members"]))
    print(" blockers=", blockers)
    assert not any(b.startswith("weapon_change:목단:") for b in blockers), (name, blockers)
    if not blockers:
        certifiable_moran.append(name)

print("MORAN_CERTIFIABLE", tuple(certifiable_moran))

print("=== CANONICAL PUBLIC FRONTIER ===")
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

print("SOURCE_CASES", len(source_cases))
print("UNIQUE_MEMBERSHIPS", len(unique))
print("CERTIFIED_COUNT", len(certified))
print("GAP_COUNT", len(gaps))
print("CERTIFIED_NAMES", tuple(name for name, _ in certified))
print("BLOCKER_FAMILIES", dict(sorted(family_counts.items())))

if not certifiable_moran:
    print("MORAN_180S_AUDIT_SKIPPED no fully certifiable public Moran membership")
else:
    audit_name = certifiable_moran[0]
    case = snapshot.SQUADS[audit_name]
    squad = spec.build_squad(list(case["members"]))
    compiled = compile_moris_squad(squad)
    cfg = spec.build_config(squad, {
        "duration": 180.0,
        "first_burst_time": 3.0,
        "rng_mode": "expected",
    })
    policy = compile_burst_policy(squad, compiled, cfg)
    enemy = EnemyStaticProfile(defense=31784.0, duration=180.0, core_px=0.0)
    score = score_static_squad(compiled, policy, enemy)
    print("MORAN_180S_AUDIT", audit_name)
    print(" squad_total", score.squad_total)
    print(" char_total", score.char_total)
    print(" events_processed", score.events_processed)
    print(" unsupported", score.unsupported)
    assert score.unsupported == ()
    assert score.squad_total > 0.0
