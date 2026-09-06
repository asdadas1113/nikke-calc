from __future__ import annotations

from pathlib import Path
from pprint import pformat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from calculator.timeline import simulate
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers


def effect_dict(e):
    keys = (
        'effect_id','actor','name','effect_type','stat','value','target','duration','max_stack',
        'max_trigger','tick_interval','bullet_lifetime','parameters','conditions','triggers'
    )
    out = {}
    for k in keys:
        if hasattr(e, k):
            v = getattr(e, k)
            if k == 'triggers':
                v = [getattr(x, '__dict__', repr(x)) for x in v]
            elif k == 'conditions':
                v = [getattr(x, '__dict__', repr(x)) for x in v]
            out[k] = v
    return out


source = []
for label, row in snapshot.SQUADS.items():
    if str(label).startswith('지그_'):
        continue
    members = tuple(row.get('members') or ())
    if len(members) != 5 or any(str(x).startswith('test_') for x in members):
        continue
    if '크라운' in members:
        source.append((label, members, row))

print('CROWN_SOURCE_COUNT', len(source))
for label, members, row in source:
    print('\n=== TEAM', label, '===')
    print('MEMBERS', members)
    squad = compile_moris_squad(spec.build_squad(list(members)))
    blockers = static_score_blockers(squad)
    print('BLOCKERS', blockers)
    crown = next(i for i, m in enumerate(squad.members) if m.name == '크라운')
    print('CROWN_ACTOR', crown)
    for e in squad.members[crown].effects:
        if '로얄 에타이어' in (e.name or ''):
            print('EFFECT', pformat(effect_dict(e), width=160, sort_dicts=False))

    moris = spec.build_squad(list(members))
    cfg = dict(row.get('config') or {})
    cfg['duration'] = min(float(cfg.get('duration', 180.0)), 20.0)
    cfg['rng_mode'] = 'expected'
    try:
        result = simulate(moris, config=cfg, verbose=True)
        log = result.log
        print('LOG_KEYS', sorted(vars(log).keys()))
        for key, value in vars(log).items():
            if not isinstance(value, list):
                continue
            matched = []
            for x in value:
                text = repr(x)
                name = getattr(x, 'name', None)
                if (name and '로얄 에타이어' in str(name)) or '로얄 에타이어' in text:
                    matched.append(x)
            if matched:
                print('LOG_MATCH', key, len(matched))
                for x in matched[:30]:
                    print(' ', getattr(x, '__dict__', repr(x)))
    except Exception as exc:
        print('SIM_ERROR', type(exc).__name__, repr(exc))
