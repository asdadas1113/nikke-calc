from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.dispatcher import TriggerDispatcher

TEAM='레이드_헬름아쿠아스노우'
moris=spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
c=compile_moris_squad(moris)
print('MEMBERS', [m.name for m in c.members])
print('BLOCKERS', static_score_blockers(c))
for e in c.effects:
    if (e.stat or '') == 'effect_interval' or any(getattr(r,'mode',None).value == 'periodic' for r in e.triggers):
        print('EFFECT', e.effect_id, c.members[e.actor].name, e.name, e.effect_type, e.stat, e.value, 'duration',e.duration,'max_stack',e.max_stack,'params',e.parameters,'target',e.target_spec.mode.value,'cap',e.capability.disposition.value,tuple(e.capability.blockers))
        for r in e.triggers:
            print('  TRIGGER', r.mode.value, r.event_key, r.interval, r.threshold, r.trigger_count_reducible)
        print('  COND', [(r.mode.value,r.key,r.value) for r in e.condition_rules])
print('SAFE PERIODICS')
for e in c.effects:
    safe=(TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported(e) or TriggerDispatcher._periodic_finite_self_crit_shape_supported(e) or TriggerDispatcher._periodic_finite_enemy_received_damage_shape_supported(e))
    if safe:
        print('SAFE',e.effect_id,c.members[e.actor].name,e.name,e.stat,[r.interval for r in e.triggers])
