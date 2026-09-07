from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calculator.timeline import _DELAYS, _MECHANICS
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.weapon import _CERTIFIED_CROSS_TYPE_WEAPON_CHANGE_DEFAULTS

print('MORIS_MG_DEFAULTS', _MECHANICS['weapon_type_defaults'].get('MG'))
print('VELVET_WC_OVERRIDE', _DELAYS.get('_weapon_change', {}).get('벨벳', {}).get('깔끔한 마무리'))
print('FAST_CROSS_DEFAULTS', _CERTIFIED_CROSS_TYPE_WEAPON_CHANGE_DEFAULTS)
team='레이드_네온벨벳'
squad=compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]['members'])))
idx=next(i for i,m in enumerate(squad.members) if m.name=='벨벳')
print('VELVET_BASE', dict(squad.members[idx].weapon))
