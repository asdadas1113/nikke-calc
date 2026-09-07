from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    StaticNormalAttackObserver, static_score_blockers,
    _charge_actor_score_safe, _rapid_to_single_charge_actor_score_safe,
)
from fast_engine.engine.shot_blocks import static_bullet_lifetime_cadence_safe
from fast_engine.engine.target_scope import possible_ally_targets

TEAM = '레이드_헬름아쿠아스노우'
DURATION = 70.0
moris = spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
compiled = compile_moris_squad(moris)
print('MEMBERS', [m.name for m in compiled.members])
print('BLOCKERS', static_score_blockers(compiled))

miranda = next(i for i,m in enumerate(compiled.members) if m.name == '미란다')
wake = next(e for e in compiled.members[miranda].effects if e.name == '웨이크업! 4')
print('WAKE', {
    'id': wake.effect_id, 'stat': wake.stat, 'value': wake.value, 'duration': wake.duration,
    'target_raw': wake.target_spec.raw, 'target_mode': wake.target_spec.mode.value,
    'triggers': [(r.mode.value, r.event_key, r.interval, r.threshold) for r in wake.triggers],
    'conditions': [(r.mode.value, r.key, r.value) for r in wake.condition_rules],
    'parameters': dict(wake.parameters),
})
print('WAKE_POSSIBLE_TARGETS', [compiled.members[i].name for i in possible_ally_targets(compiled, wake)])
for actor in possible_ally_targets(compiled, wake):
    print('WAKE_TARGET_SAFETY', compiled.members[actor].name,
          'static', static_bullet_lifetime_cadence_safe(compiled, actor),
          'charge', _charge_actor_score_safe(compiled, actor),
          'rapid_single_charge', _rapid_to_single_charge_actor_score_safe(compiled, actor))

for e in compiled.effects:
    mode = e.target_spec.mode.value
    if mode in {'top_atk','top_atk_excl_self','lowest_atk_burst3'} or (e.stat or '') in {
        'atk_pct','atk_flat','atk_caster_based_pct','atk_from_hp_pct','atk_copy','atk_buff_mag_pct'
    }:
        print('EFFECT', {
            'id': e.effect_id,
            'actor': compiled.members[e.actor].name,
            'name': e.name,
            'type': e.effect_type,
            'stat': e.stat,
            'value': e.value,
            'duration': e.duration,
            'target_raw': e.target_spec.raw,
            'target_mode': mode,
            'triggers': [(r.mode.value, r.event_key, r.interval, r.threshold) for r in e.triggers],
            'conditions': [(r.mode.value, r.key, r.value) for r in e.condition_rules],
            'parameters': dict(e.parameters),
        })

resolutions = []
orig_resolve = BuffManager._resolve_target

def traced_resolve(self, raw, caster, *args, **kwargs):
    result = orig_resolve(self, raw, caster, *args, **kwargs)
    if isinstance(raw, str) and ('top_atk' in raw or 'lowest_atk' in raw):
        resolutions.append((float(getattr(self, '_cur_t', -1.0)), caster, raw, tuple(result)))
    return result

with patch.object(BuffManager, '_resolve_target', new=traced_resolve):
    simulate(moris, config={'duration': DURATION, 'rng_mode': 'expected'}, enemy=dict(DEFAULT_ENEMY), verbose=True)

print('MORIS_RANK_RESOLUTIONS')
for row in resolutions:
    print(row)

fast_targets = []
orig_shape = TriggerDispatcher._lazy_rank_target_shape_supported
orig_activate_one = ActiveEffectStore._activate_one

def diagnostic_shape(effect):
    return orig_shape(effect) or effect.effect_id == wake.effect_id

def traced_activate_one(self, effect, target, cohort, now, scheduler, **kwargs):
    if effect.effect_id == wake.effect_id:
        fast_targets.append((float(now), self.squad.members[target].name, tuple(self.squad.members[i].name for i in cohort)))
    return orig_activate_one(self, effect, target, cohort, now, scheduler, **kwargs)

policy = compile_burst_policy(moris, compiled, {'duration': DURATION})
enemy = EnemyStaticProfile(
    defense=float(DEFAULT_ENEMY.get('def', 31784.0)),
    element=DEFAULT_ENEMY.get('code'),
    core_px=float(DEFAULT_ENEMY.get('core_px', 0.0) or 0.0),
    duration=DURATION,
)
sink = SimpleDamageScoreSink(compiled, enemy)
with patch.object(TriggerDispatcher, '_lazy_rank_target_shape_supported', new=staticmethod(diagnostic_shape)), patch.object(ActiveEffectStore, '_activate_one', new=traced_activate_one):
    runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
    observer = StaticNormalAttackObserver(runtime, duration=DURATION)
    runtime.run(duration=DURATION, score_observer=observer)
print('FAST_FORCED_LAZY_TARGETS', fast_targets)
print('FAST_PENDING_END', runtime.dispatcher.effects._pending_target)
