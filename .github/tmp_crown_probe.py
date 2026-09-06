from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from calculator.timeline import simulate

team='레이드_아스카루드밀라'
row=snapshot.SQUADS[team]
moris=spec.build_squad(list(row['members']))
result=simulate(moris, config={'duration':60.0,'rng_mode':'expected'}, verbose=True)
print('TEAM', team, row['members'])
print('INSTANT HEALS')
for x in result.log.instant_events:
    if x.name in {'우정의 서포트 2','로얄 에타이어 3'}:
        print(vars(x))
print('ROYAL 4 ACTIVATIONS')
for x in result.log.buff_events:
    if x.name=='로얄 에타이어 4' and x.kind=='activate':
        print(vars(x))

patterns=('lowest_hp','LOWEST_HP','allies_lowest_hp','hp_ratio','current_hp')
for path in ('calculator/effects.py','calculator/targets.py','calculator/timeline.py','calculator/state.py','fast_engine/engine/targets.py','fast_engine/engine/target_scope.py'):
    p=ROOT/path
    if not p.exists():
        continue
    lines=p.read_text(encoding='utf-8').splitlines()
    hits=[i for i,line in enumerate(lines,1) if any(q in line for q in patterns)]
    if not hits:
        continue
    print('\nFILE',path,'HITS',hits)
    shown=set()
    for h in hits:
        a=max(1,h-15); b=min(len(lines),h+25)
        if any(a>=x and b<=y for x,y in shown): continue
        shown.add((a,b))
        print('---',a,b,'---')
        for n in range(a,b+1): print(f'{n:04d}: {lines[n-1]}')
