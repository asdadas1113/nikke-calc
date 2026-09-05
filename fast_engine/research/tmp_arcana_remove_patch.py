from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import static_score_blockers

source_cases = []
unique = {}
for source_name, case in snapshot.SQUADS.items():
    if str(source_name).startswith('지그_'):
        continue
    members = tuple(str(m) for m in case['members'])
    if len(members) != 5 or any(m.startswith('test_') for m in members):
        continue
    source_cases.append((str(source_name), members))
    unique.setdefault(members, str(source_name))

counts = Counter()
certified = []
gaps = []
owned_removers = []
all_removers = 0
arcana_rows = []

for members, source_name in unique.items():
    compiled = compile_moris_squad(spec.build_squad(list(members)))
    blockers = static_score_blockers(compiled)
    if blockers:
        gaps.append((source_name, members, blockers))
    else:
        certified.append((source_name, members))
    for blocker in blockers:
        counts[blocker.split(':', 1)[0]] += 1
    for effect in compiled.effects:
        if (effect.stat or '') != 'remove_named_buff':
            continue
        all_removers += 1
        if TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(compiled, effect):
            row = (source_name, compiled.members[effect.actor].name, effect.name, effect.parameters.get('target_effect'))
            owned_removers.append(row)
        if compiled.members[effect.actor].name == '아르카나 : 포츈 메이트':
            arcana_rows.append((
                source_name,
                effect.name,
                effect.parameters.get('target_effect'),
                TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(compiled, effect),
                tuple(b for b in blockers if '아르카나 : 포츈 메이트' in b),
            ))

print('PROMOTION_SOURCE_CASES', len(source_cases))
print('PROMOTION_UNIQUE_MEMBERSHIPS', len(unique))
print('PROMOTION_CERTIFIED', len(certified), [name for name, _ in certified])
print('PROMOTION_GAPS', len(gaps))
print('PROMOTION_BLOCKERS', dict(sorted(counts.items())))
print('PROMOTION_REMOVE_NAMED_TOTAL', all_removers)
print('PROMOTION_OWNED_REMOVERS', owned_removers)
print('PROMOTION_ARCANA_ROWS', arcana_rows)
