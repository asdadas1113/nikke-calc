from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from context import snapshot,spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import _possible_ally_targets
from fast_engine.engine.conditions import ConditionMode
from fast_engine.engine.triggers import TriggerMode

for team in ("스쿼드2","레이드_네온벨벳","레이드_소다"):
    squad=compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]["members"])))
    actor=next(i for i,m in enumerate(squad.members) if m.name=="나유타")
    member=squad.members[actor]
    effect=next(e for e in member.effects if e.name=="기억 연소")
    print('\nTEAM',team,flush=True)
    print('member',member.burst_cooldown,member.weapon,flush=True)
    print('effect cap',effect.capability.disposition.value,effect.capability.blockers,flush=True)
    print('effect fields',effect.effect_type,effect.target_spec.mode.value,effect.target_spec.runtime_supported,effect.duration,effect.max_stack,effect.max_trigger,effect.tick_interval,effect.parameters,flush=True)
    print('shape',TriggerDispatcher._temporary_self_rapid_to_charge_skill_weapon_change_shape_supported(effect),flush=True)
    print('related',[(e.effect_id,e.name,e.parameters) for e in squad.effects if e.effect_type=='weapon_change' and actor in _possible_ally_targets(squad,e)],flush=True)
    refs=[]
    for other in squad.effects:
        if other.effect_id==effect.effect_id: continue
        name=effect.name
        references=(any(r.key==name for r in other.condition_rules) or any((r.event_key or '')==f'event:state_end:{name}' for r in other.triggers) or other.parameters.get('target_effect')==name or other.parameters.get('scaling_ref')==name)
        if references:
            refs.append(other)
            print('consumer',other.effect_id,other.name,other.effect_type,other.stat,other.target_spec.mode.value,other.target_spec.runtime_supported,other.value,other.duration,other.max_stack,other.max_trigger,other.tick_interval,other.parameters,[(r.mode.value,r.key,r.value) for r in other.condition_rules],[(r.mode.value,r.event_key,r.threshold) for r in other.triggers],flush=True)
    print('refs',len(refs),flush=True)
    print('all full/onattack',[(e.effect_id,e.name,e.effect_type,e.stat,[(r.mode.value,r.event_key) for r in e.triggers],TriggerDispatcher.is_executable_effect(e)) for e in member.effects if any(r.event_key in {'full_charge_hit','on_attack'} for r in e.triggers)],flush=True)
