from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.target_scope import possible_ally_targets


def describe(effect, squad):
    return {
        'id': effect.effect_id,
        'actor': squad.members[effect.actor].name,
        'name': effect.name,
        'stat': effect.stat,
        'type': effect.effect_type,
        'value': effect.value,
        'target': effect.target,
        'targets': tuple(squad.members[i].name for i in possible_ally_targets(squad, effect)),
        'duration': effect.duration,
        'max_stack': effect.max_stack,
        'parameters': dict(effect.parameters),
        'conditions': tuple(repr(x) for x in effect.condition_rules),
        'triggers': tuple(repr(x) for x in effect.triggers),
        'self_stack_owned': TriggerDispatcher._self_stack_heal_chain_shape_supported(squad, effect) if (effect.stat or '') == 'heal_hp_pct' else False,
        'runtime_exec': TriggerDispatcher.is_executable_effect(effect),
    }

for label, row in snapshot.SQUADS.items():
    if str(label).startswith('지그_'):
        continue
    members = tuple(row.get('members') or ())
    if len(members) != 5 or '크라운' not in members:
        continue
    squad = compile_moris_squad(spec.build_squad(list(members)))
    crown = next(i for i,m in enumerate(squad.members) if m.name == '크라운')
    consumer = next(e for e in squad.members[crown].effects if e.name == '로얄 에타이어 4')
    providers = tuple(
        e for e in squad.effects
        if e.effect_id != consumer.effect_id
        and (e.stat or '') in {'heal_hp_pct','lifesteal_pct'}
        and crown in possible_ally_targets(squad, e)
    )
    print('\n===', label, '===')
    print('HEAL_DEP_SAFE', TriggerDispatcher.heal_received_dependency_score_safe(squad, consumer))
    print('PROVIDER_COUNT', len(providers))
    for p in providers:
        print('PROVIDER', describe(p, squad))
