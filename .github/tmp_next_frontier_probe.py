from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.target_scope import possible_ally_targets
from fast_engine.research.public_blocker_frontier import scan_public_blockers

r = scan_public_blockers()
rows = sorted(r['rows'], key=lambda x: (len(x['blockers']) + len(x['unsupported']), x['source_name']))
fam = Counter(b.split(':', 1)[0] for row in r['rows'] for b in row['blockers'])
print('COUNTS', r['team_count'], r['certified_team_count'], r['coverage_gap_count'])
print('FAMILIES', sorted(fam.items()))
for row in rows[:12]:
    if not row['blockers'] and not row['unsupported']:
        continue
    print('ROW', row['source_name'], 'N', len(row['blockers']), 'U', len(row['unsupported']))
    for b in row['blockers']:
        print('  B', b)

CANDIDATES = {
    '레이드_라피앨리스': [('앨리스', '힘나는 당근')],
    '레이드_앨리스브래디': [('앨리스', '힘나는 당근')],
    '스쿼드5': [('신데렐라', '무결한 유리'), ('크라운', '로얄 에타이어 4')],
    '레이드_루주': [('신데렐라', '무결한 유리')],
    '스쿼드1': [('크라운', '로얄 에타이어 4'), ('리틀 머메이드', '거품 난사')],
    '레이드_네온벨벳': [('벨벳', '깔끔한 마무리')],
}

def effect_dict(squad, effect):
    return {
        'id': effect.effect_id,
        'actor': squad.members[effect.actor].name,
        'name': effect.name,
        'type': effect.effect_type,
        'stat': effect.stat,
        'value': effect.value,
        'duration': effect.duration,
        'max_stack': effect.max_stack,
        'max_trigger': effect.max_trigger,
        'tick': effect.tick_interval,
        'target_raw': effect.target_spec.raw,
        'target_mode': effect.target_spec.mode.value,
        'triggers': [(x.mode.value, x.event_key, x.threshold, x.interval) for x in effect.triggers],
        'conditions': [(x.mode.value, x.key, x.value) for x in effect.condition_rules],
        'parameters': dict(effect.parameters),
        'capability': (effect.capability.disposition.value, list(effect.capability.blockers)),
        'possible_targets': [squad.members[i].name for i in possible_ally_targets(squad, effect)],
    }

for team, wanted in CANDIDATES.items():
    squad = compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]['members'])))
    print('TEAM', team, [m.name for m in squad.members])
    print('BLOCKERS', static_score_blockers(squad))
    for actor_name, effect_name in wanted:
        print('CANDIDATE', actor_name, effect_name)
        for effect in squad.effects:
            if squad.members[effect.actor].name == actor_name and effect.name == effect_name:
                print(' EFFECT', effect_dict(squad, effect))
        actor = next((i for i,m in enumerate(squad.members) if m.name == actor_name), None)
        if actor is not None:
            print(' ACTOR_EFFECTS')
            for effect in squad.members[actor].effects:
                print('  ', effect_dict(squad, effect))
