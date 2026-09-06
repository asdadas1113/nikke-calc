from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

seen: set[tuple[str, ...]] = set()
source_cases = 0
certified: list[str] = []
families: Counter[str] = Counter()
exact: Counter[str] = Counter()
gaps: list[tuple[str, tuple[str, ...]]] = []
for name, case in snapshot.SQUADS.items():
    if str(name).startswith("지그_"):
        continue
    members = tuple(case["members"])
    if len(members) != 5 or any(str(member).startswith("test_") for member in members):
        continue
    source_cases += 1
    if members in seen:
        continue
    seen.add(members)
    compiled = compile_moris_squad(spec.build_squad(list(members)))
    blockers = static_score_blockers(compiled)
    if blockers:
        gaps.append((str(name), blockers))
    else:
        certified.append(str(name))
    for blocker in blockers:
        exact[blocker] += 1
        families[blocker.split(":", 1)[0]] += 1

print("FRONTIER", source_cases, len(seen), len(certified), len(gaps), flush=True)
print("CERTIFIED", tuple(certified), flush=True)
print("FAMILIES", dict(sorted(families.items())), flush=True)
print("TOP_EXACT", flush=True)
for blocker, count in exact.most_common(30):
    print(count, blocker, flush=True)
print("GAPS", flush=True)
for name, blockers in gaps:
    print(name, len(blockers), blockers, flush=True)

assert source_cases == 24
assert len(seen) == 23
assert len(certified) == 6
assert len(gaps) == 17
assert families["cadence"] == 53
assert families["weapon_change"] == 7
