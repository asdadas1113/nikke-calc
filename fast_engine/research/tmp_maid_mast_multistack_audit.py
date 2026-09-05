from __future__ import annotations

from dataclasses import asdict, is_dataclass

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

TARGET = '마스트 : 로망틱 메이드'
STATE = '취기'


def show_effect(e):
    return {
        'id': e.effect_id,
        'actor': e.actor,
        'name': e.name,
        'stat': e.stat,
        'value': e.value,
        'duration': e.duration,
        'max_stack': e.max_stack,
        'max_trigger': e.max_trigger,
        'tick_interval': e.tick_interval,
        'trigger': repr(e.trigger),
        'raw_trigger': getattr(e, 'raw_trigger', None),
        'target': repr(e.target),
        'target_spec': repr(getattr(e, 'target_spec', None)),
        'conditions': [repr(r) for r in e.condition_rules],
        'params': dict(e.parameters or {}),
    }

source = []
for label, cfg in snapshot.SQUADS.items():
    if str(label).startswith('지그_'):
        continue
    members = tuple(str(m) for m in cfg['members'])
    if len(members) != 5 or any(m.startswith('test_') for m in members):
        continue
    if TARGET in members:
        source.append((str(label), members))

print('MAID_MAST_PUBLIC', source)
for label, members in source:
    squad = spec.build_squad(list(members))
    compiled = compile_moris_squad(squad)
    actor = compiled.names.index(TARGET)
    print('\n===', label, members, '===')
    for e in compiled.members[actor].effects:
        if STATE in e.name or STATE in str(e.parameters) or '파이레츠 스피릿' in e.name:
            print('OWN', show_effect(e))
    for e in compiled.effects:
        refs = ' '.join([e.name, str(e.parameters), ' '.join(repr(r) for r in e.condition_rules)])
        if STATE in refs and e.actor != actor:
            print('EXTERNAL_REF', compiled.members[e.actor].name, show_effect(e))
        elif STATE in refs and e.actor == actor and not (STATE in e.name or '파이레츠 스피릿' in e.name):
            print('SELF_REF', show_effect(e))
    print('BLOCKERS', [b for b in static_score_blockers(compiled) if TARGET in b])

    cfg = dict(snapshot.SQUADS[label].get('config', {}))
    cfg.update({'duration': 45.0, 'rng_mode': 'expected'})
    result = simulate(squad, config=cfg, seed=42, verbose=True)
    be = [e for e in result.log.buff_events if STATE in e.name or '파이레츠 스피릿' in e.name]
    print('BUFF_EVENTS')
    for e in be:
        print(vars(e) if hasattr(e, '__dict__') else e)
    print('BURST_LOG')
    for e in result.log.burst_log:
        print(vars(e) if hasattr(e, '__dict__') else e)

# Controls: keep Maid Mast and swap likely B1/B2/B3 peers to see whether condition is roster- or runtime-driven.
controls = [
    ['아니스 : 스타', '앵커 : 이노센트 메이드', TARGET, '앨리스', '브래디'],
    ['리틀 머메이드', '앵커 : 이노센트 메이드', TARGET, '앨리스', '브래디'],
    ['목단', TARGET, '홍련 : 흑영', '리버렐리오', '앵커 : 이노센트 메이드'],
]
for members in controls:
    squad = spec.build_squad(members)
    compiled = compile_moris_squad(squad)
    actor = compiled.names.index(TARGET)
    print('\n=== CONTROL', members, '===')
    for e in compiled.members[actor].effects:
        if STATE in e.name or STATE in str(e.parameters) or '파이레츠 스피릿' in e.name:
            print('OWN', show_effect(e))
    result = simulate(squad, config={'duration': 30.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'}, seed=42, verbose=True)
    for e in result.log.buff_events:
        if STATE in e.name or '파이레츠 스피릿' in e.name:
            print('BUFF', vars(e) if hasattr(e, '__dict__') else e)
