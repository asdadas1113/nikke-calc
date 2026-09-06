from __future__ import annotations

from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

patterns=('allies_lowest_hp','lowest_hp','_resolve_target','state["hp"]','hp_ratio')
for p in sorted((ROOT/'calculator').glob('*.py')):
    lines=p.read_text(encoding='utf-8').splitlines()
    hits=[i for i,line in enumerate(lines,1) if any(q in line for q in patterns)]
    if not hits: continue
    print('\nFILE',p.relative_to(ROOT),'HITS',hits)
    covered=[]
    for h in hits:
        a=max(1,h-20); b=min(len(lines),h+30)
        if any(a>=x and b<=y for x,y in covered): continue
        covered.append((a,b))
        print('---',a,b,'---')
        for n in range(a,b+1): print(f'{n:04d}: {lines[n-1]}')
