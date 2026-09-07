from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad

for team in ('레이드_작열짬','레이드_헬름아쿠아스노우'):
    squad=compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]['members'])))
    print('TEAM',team)
    for i,m in enumerate(squad.members):
        if m.weapon.get('weapon_type')=='MG':
            print(' MG',i,m.name,dict(m.weapon))
