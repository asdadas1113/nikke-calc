from __future__ import annotations

from dataclasses import asdict, is_dataclass
from unittest.mock import patch

from calculator.buff_manager import BuffManager
from calculator.timeline import DEFAULT_ENEMY, simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import static_score_blockers

TEAM = '레이드_헬름아쿠아스노우'
DURATION = 70.0
moris = spec.build_squad(list(snapshot.SQUADS[TEAM]['members']))
compiled = compile_moris_squad(moris)
print('MEMBERS', [m.name for m in compiled.members])
print('BLOCKERS', static_score_blockers(compiled))

miranda = next(i for i,m in enumerate(compiled.members) if m.name == '미란다')
rank_effects = []
for e in compiled.effects:
    mode = e.target_spec.mode.value
    if mode in {'top_atk','top_atk_excl_self','lowest_atk_burst3'} or (e.stat or '') in {
        'atk_pct','atk_flat','atk_caster_based_pct','atk_from_hp_pct','atk_copy','atk_buff_mag_pct'
    }:
        rank_effects.append(e)
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

wake = next(e for e in compiled.members[miranda].effects if e.name == '웨이크업! 4')
print('WAKE', {
    'id': wake.effect_id, 'stat': wake.stat, 'value': wake.value, 'duration': wake.duration,
    'target_raw': wake.target_spec.raw, 'target_mode': wake.target_spec.mode.value,
    'triggers': [(r.mode.value, r.event_key, r.interval, r.threshold) for r in wake.triggers],
    'conditions': [(r.mode.value, r.key, r.value) for r in wake.condition_rules],
    'parameters': dict(wake.parameters),
})

# Moris lazy rank target oracle. The resolver is called when the lazy buff is
# actually consumed after same-frame buffs have been registered.
resolutions = []
activations = []
orig_resolve = BuffManager._resolve_target
orig_activate = BuffManager._activate

def traced_resolve(self, raw, caster, *args, **kwargs):
    result = orig_resolve(self, raw, caster, *args, **kwargs)
    if isinstance(raw, str) and ('top_atk' in raw or 'lowest_atk' in raw):
        resolutions.append((float(getattr(self, '_cur_t', -1.0)), caster, raw, tuple(result)))
    return result

def traced_activate(self, eff, caster, t, suppress_event=False):
    if caster == '미란다' or eff.get('name') == '웨이크업! 4':
        activations.append((float(t), caster, eff.get('name'), eff.get('stat'), eff.get('target'), eff.get('fixed_value'), eff.get('values')))
    return orig_activate(self, eff, caster, t, suppress_event=suppress_event)

with patch.object(BuffManager, '_resolve_target', new=traced_resolve), patch.object(BuffManager, '_activate', new=traced_activate):
    result = simulate(moris, config={'duration': DURATION, 'rng_mode': 'expected'}, enemy=dict(DEFAULT_ENEMY), verbose=True)

print('MORIS_ACTIVATIONS')
for row in activations:
    print(row)
print('MORIS_RANK_RESOLUTIONS')
for row in resolutions:
    print(row)
print('MORIS_WAKE_BUFF_EVENTS')
for row in result.log.buff_events:
    if row.name == '웨이크업! 4' or row.caster == '미란다':
        print(vars(row) if hasattr(row, '__dict__') else row)
print('MORIS_BURSTS')
for row in result.log.burst_log:
    print((row.t, row.event, row.caster))
