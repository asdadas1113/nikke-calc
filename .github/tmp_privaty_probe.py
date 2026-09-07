from __future__ import annotations
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from context import snapshot,spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

seen={}; source_cases=0; certified=[]; families=Counter(); exact=Counter(); gaps=[]
for name,case in snapshot.SQUADS.items():
    if str(name).startswith('지그_'): continue
    members=tuple(case['members'])
    if len(members)!=5 or any(str(x).startswith('test_') for x in members): continue
    source_cases+=1
    if members in seen: continue
    seen[members]=str(name)
    compiled=compile_moris_squad(spec.build_squad(list(members)))
    blockers=static_score_blockers(compiled)
    if not blockers: certified.append(str(name))
    else: gaps.append((str(name),blockers))
    for b in blockers:
        families[b.split(':',1)[0]]+=1; exact[b]+=1
print('FRONTIER',source_cases,len(seen),len(certified),len(seen)-len(certified),flush=True)
print('CERTIFIED',tuple(certified),flush=True)
print('FAMILIES',dict(sorted(families.items())),flush=True)
print('TOP_EXACT',flush=True)
for blocker,count in exact.most_common(40): print(count,blocker,flush=True)
print('PRIVATY',flush=True)
for name,blockers in gaps:
    rows=tuple(b for b in blockers if ':프리바티:' in b)
    if rows: print(name,rows,flush=True)
