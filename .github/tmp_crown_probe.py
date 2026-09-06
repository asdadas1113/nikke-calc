from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from context import snapshot,spec
from fast_engine.engine.compiler import compile_moris_squad

stats={}
for label,row in snapshot.SQUADS.items():
    members=tuple(row.get('members') or ())
    if len(members)!=5: continue
    try: squad=compile_moris_squad(spec.build_squad(list(members)))
    except Exception: continue
    for e in squad.effects:
        s=e.stat or ''
        if any(k in s.lower() for k in ('hp','heal','life','shield')):
            stats.setdefault(s,[]).append((label,squad.members[e.actor].name,e.name,e.effect_type,e.target))
print('HEALTH_STATS')
for s,rows in sorted(stats.items()):
    print('\nSTAT',repr(s),'COUNT',len(rows))
    for x in rows[:12]: print(' ',x)

for path in sorted((ROOT/'fast_engine/engine').glob('*.py')):
    lines=path.read_text(encoding='utf-8').splitlines()
    hits=[]
    for i,line in enumerate(lines,1):
        low=line.lower()
        if ('.hp' in low or ' hp ' in low or 'heal_hp_pct' in low or 'current_hp' in low) and ('=' in line or 'def ' in line or 'stat' in line): hits.append(i)
    if hits:
        print('\nFILE',path.relative_to(ROOT),'HITS',hits)
        for h in hits[:30]:
            a=max(1,h-4); b=min(len(lines),h+7)
            for n in range(a,b+1): print(f'{n:04d}: {lines[n-1]}')
            print('---')
