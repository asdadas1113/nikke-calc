from __future__ import annotations

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerMode

members = list(snapshot.SQUADS['스쿼드3']['members'])
compiled = compile_moris_squad(spec.build_squad(members))
actor = members.index('아르카나 : 포츈 메이트')

for effect in compiled.members[actor].effects:
    if effect.name not in {'쌓여가는 사진첩 2', '쌓여가는 사진첩 3'}:
        continue
    name = effect.parameters.get('target_effect')
    print('\n=== REMOVER', effect.name, 'target_effect=', name, '===')
    checks = {
        'effect_type': effect.effect_type == 'instant',
        'stat': (effect.stat or '') == 'remove_named_buff',
        'target_self': effect.target_spec.mode is TargetMode.SELF,
        'target_runtime': effect.target_spec.runtime_supported,
        'value_none': effect.value is None,
        'duration_none': effect.duration is None,
        'max_stack_none': effect.max_stack is None,
        'max_trigger_none': effect.max_trigger is None,
        'tick_none': effect.tick_interval is None,
        'name_string': isinstance(name, str) and bool(name),
        'params_exact': set(effect.parameters) == {'target_effect'},
        'no_conditions': not effect.condition_rules,
        'one_trigger': len(effect.triggers) == 1,
        'trigger_event': len(effect.triggers) == 1 and effect.triggers[0].mode is TriggerMode.EVENT,
        'trigger_fb_end': len(effect.triggers) == 1 and effect.triggers[0].event_key == 'full_burst_end',
    }
    print('REMOVER_FIELDS', {
        'effect_type': effect.effect_type, 'stat': effect.stat, 'target': effect.target,
        'target_mode': effect.target_spec.mode.value, 'target_runtime_supported': effect.target_spec.runtime_supported,
        'value': effect.value, 'duration': effect.duration, 'max_stack': effect.max_stack,
        'max_trigger': effect.max_trigger, 'tick_interval': effect.tick_interval,
        'parameters': dict(effect.parameters), 'conditions': effect.conditions,
        'triggers': [(r.raw, r.event_key, r.mode.value) for r in effect.triggers],
        'capability': (effect.capability.disposition.value, tuple(effect.capability.blockers)),
    })
    print('REMOVER_CHECKS', checks)

    providers = tuple(p for p in compiled.effects if p.effect_id != effect.effect_id and p.name == name)
    print('PROVIDER_COUNT', len(providers))
    for provider in providers:
        pchecks = {
            'same_actor': provider.actor == effect.actor,
            'buff': provider.effect_type == 'buff',
            'stat_allowed': (provider.stat or '') in {'crit_rate', 'atk_dmg_pct'},
            'target_self': provider.target_spec.mode is TargetMode.SELF,
            'target_runtime': provider.target_spec.runtime_supported,
            'value_present': provider.value is not None,
            'permanent': provider.duration in (None, -1, -1.0),
            'one_stack': provider.max_stack in (None, 1, 1.0),
            'max_trigger_none': provider.max_trigger is None,
            'tick_none': provider.tick_interval is None,
            'no_params': not provider.parameters,
            'no_conditions': not provider.condition_rules,
            'one_trigger': len(provider.triggers) == 1,
            'trigger_event': len(provider.triggers) == 1 and provider.triggers[0].mode is TriggerMode.EVENT,
            'trigger_burst_cast': len(provider.triggers) == 1 and provider.triggers[0].event_key == 'burst_cast',
            'direct_supported': is_direct_damage_buff_runtime_supported(provider),
            'dispatcher_executable': TriggerDispatcher.is_executable_effect(provider),
        }
        print('PROVIDER', provider.effect_id, provider.name, {
            'actor': provider.actor, 'effect_type': provider.effect_type, 'stat': provider.stat,
            'target': provider.target, 'target_mode': provider.target_spec.mode.value,
            'target_runtime_supported': provider.target_spec.runtime_supported,
            'value': provider.value, 'duration': provider.duration, 'max_stack': provider.max_stack,
            'max_trigger': provider.max_trigger, 'tick_interval': provider.tick_interval,
            'parameters': dict(provider.parameters), 'conditions': provider.conditions,
            'triggers': [(r.raw, r.event_key, r.mode.value) for r in provider.triggers],
            'capability': (provider.capability.disposition.value, tuple(provider.capability.blockers)),
        })
        print('PROVIDER_CHECKS', pchecks)

    state_end_key = f'event:state_end:{name}'
    state_end_consumers = [
        (o.effect_id, compiled.members[o.actor].name, o.name, o.stat,
         [(r.raw, r.event_key) for r in o.triggers])
        for o in compiled.effects if o.effect_id != effect.effect_id
        and any((r.event_key or '') == state_end_key for r in o.triggers)
    ]
    condition_consumers = [
        (o.effect_id, compiled.members[o.actor].name, o.name, o.stat,
         [(r.raw, r.key) for r in o.condition_rules])
        for o in compiled.effects if o.effect_id != effect.effect_id
        and any(r.key == name for r in o.condition_rules)
    ]
    mutators = [
        (o.effect_id, compiled.members[o.actor].name, o.name, o.stat, dict(o.parameters))
        for o in compiled.effects if o.effect_id != effect.effect_id
        and o.parameters.get('target_effect') == name
    ]
    print('STATE_END_CONSUMERS', state_end_consumers)
    print('CONDITION_CONSUMERS', condition_consumers)
    print('OTHER_MUTATORS', mutators)
