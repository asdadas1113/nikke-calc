from __future__ import annotations

# Temporary trigger/probe retained only until the Moran checkpoint clean gate.
from collections import Counter
from pathlib import Path
import signal
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

class ProbeTimeout(RuntimeError):
    pass

def _alarm(_sig, _frame):
    raise ProbeTimeout("Moran 180s score exceeded 20s")

signal.signal(signal.SIGALRM, _alarm)

# Canonical public frontier audit.
seen: dict[tuple[str, ...], str] = {}
source_cases = 0
certified: list[str] = []
families: Counter[str] = Counter()
for name, case in snapshot.SQUADS.items():
    if str(name).startswith("지그_"):
        continue
    members = tuple(case["members"])
    if len(members) != 5 or any(str(member).startswith("test_") for member in members):
        continue
    source_cases += 1
    if members in seen:
        continue
    seen[members] = str(name)
    squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(squad)
    blockers = static_score_blockers(compiled)
    if not blockers:
        certified.append(str(name))
    for blocker in blockers:
        families[blocker.split(":", 1)[0]] += 1

print("FRONTIER source_cases", source_cases, "unique", len(seen), "certified", len(certified), "gaps", len(seen) - len(certified), flush=True)
print("CERTIFIED", tuple(certified), flush=True)
print("FAMILIES", dict(sorted(families.items())), flush=True)
assert source_cases == 24
assert len(seen) == 23
assert len(certified) == 6
assert len(seen) - len(certified) == 17
assert families["cadence"] == 53

# Full 180s production score for the newly certified Moran membership.
case = snapshot.SQUADS["스쿼드4"]
squad = spec.build_squad(list(case["members"]))
compiled = compile_moris_squad(squad)
blockers = static_score_blockers(compiled)
assert blockers == (), blockers
cfg = spec.build_config(squad, {
    "duration": 180.0,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
})
policy = compile_burst_policy(squad, compiled, cfg)
enemy = EnemyStaticProfile(defense=31784.0, duration=180.0, core_px=0.0)
t0 = perf_counter()
signal.alarm(20)
try:
    score = score_static_squad(compiled, policy, enemy)
finally:
    signal.alarm(0)
elapsed = perf_counter() - t0
print("MORAN_180 elapsed", elapsed, "events", score.events_processed, "total", score.squad_total, "chars", score.char_total, "unsupported", score.unsupported, flush=True)
assert score.unsupported == ()
