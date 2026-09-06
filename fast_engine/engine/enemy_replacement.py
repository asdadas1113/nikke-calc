from __future__ import annotations

from dataclasses import dataclass

from .conditions import ConditionMode
from .targets import TargetMode
from .triggers import TriggerMode


@dataclass(frozen=True, slots=True)
class CertifiedEnemyReplacementLifecycle:
    actor: int
    source_effect_id: int
    replacement_effect_id: int
    control_effect_id: int
    remover_effect_id: int
    threshold: int


def _permanent_enemy_received(effect) -> bool:
    return (
        effect.effect_type == "buff"
        and (effect.stat or "") == "received_dmg_pct"
        and effect.target_spec.mode is TargetMode.ENEMY
        and effect.target_spec.runtime_supported
        and effect.value is not None
        and float(effect.value) > 0.0
        and effect.duration in (None, -1, -1.0)
        and effect.max_stack in (None, 1, 1.0)
        and effect.max_trigger is None
        and effect.tick_interval is None
        and not effect.parameters
        and str(effect.polarity or "").startswith("harmful")
    )


def _hit_replace_gate(effect, source_name: str) -> int | None:
    if (
        len(effect.triggers) != 1
        or len(effect.condition_rules) != 1
        or effect.condition_rules[0].mode is not ConditionMode.TARGET_STATE
        or effect.condition_rules[0].key != source_name
    ):
        return None
    rule=effect.triggers[0]
    if (
        rule.mode is not TriggerMode.MODULO
        or rule.event_key != "hit_count"
        or not rule.trigger_count_reducible
    ):
        return None
    threshold=int(rule.threshold or 0)
    return threshold if threshold > 0 and abs(float(rule.threshold or 0)-threshold) <= 1e-9 else None


def certified_enemy_received_damage_replacements(squad) -> tuple[CertifiedEnemyReplacementLifecycle, ...]:
    """Prove one permanent enemy received-damage state is replaced, not stacked.

    The owned graph is deliberately narrow: enemy-spawn source -> same-value
    permanent replacement on a reducible hit-count gate -> score-unobserved
    finite enemy stun sibling -> same-gate named remover. Runtime owns only the
    remover; generic enemy stun and generic named removal remain closed.
    """
    rows=[]
    for remover in squad.effects:
        source_name=remover.parameters.get("target_effect")
        if not (
            remover.effect_type == "instant"
            and (remover.stat or "") == "remove_named_buff"
            and remover.target_spec.mode is TargetMode.ENEMY
            and remover.target_spec.runtime_supported
            and remover.value is None
            and remover.duration is None
            and remover.max_stack is None
            and remover.max_trigger is None
            and remover.tick_interval is None
            and isinstance(source_name,str) and source_name
            and set(remover.parameters)=={"target_effect"}
        ):
            continue
        providers=tuple(e for e in squad.effects if e.name==source_name and e.effect_id!=remover.effect_id)
        if len(providers)!=1:
            continue
        source=providers[0]
        if not _permanent_enemy_received(source):
            continue
        if not (
            len(source.triggers)==1
            and source.triggers[0].mode is TriggerMode.EVENT
            and source.triggers[0].event_key == "event:enemy_spawn"
            and not source.condition_rules
        ):
            continue
        if source.actor != remover.actor:
            continue
        actor_effects=tuple(squad.members[source.actor].effects)
        pos={e.effect_id:i for i,e in enumerate(actor_effects)}
        p=pos.get(source.effect_id); r=pos.get(remover.effect_id)
        if p is None or r != p+3 or p+3 >= len(actor_effects):
            continue
        replacement=actor_effects[p+1]; control=actor_effects[p+2]
        threshold=_hit_replace_gate(replacement,source_name)
        if threshold is None or _hit_replace_gate(control,source_name)!=threshold or _hit_replace_gate(remover,source_name)!=threshold:
            continue
        if not _permanent_enemy_received(replacement):
            continue
        if not (
            replacement.actor==source.actor
            and replacement.name and replacement.name != source.name
            and replacement.stat==source.stat
            and abs(float(replacement.value or 0)-float(source.value or 0)) <= 1e-9
            and replacement.polarity==source.polarity
        ):
            continue
        if not (
            control.actor==source.actor
            and control.effect_type=="buff"
            and (control.stat or "")=="stun"
            and control.target_spec.mode is TargetMode.ENEMY
            and control.target_spec.runtime_supported
            and control.duration is not None and float(control.duration)>0.0
            and control.max_stack in (None,1,1.0)
            and control.max_trigger is None
            and control.tick_interval is None
            and not control.parameters
            and control.name and control.name not in {source.name,replacement.name}
        ):
            continue
        names={source.name,replacement.name,control.name}
        unsafe=False
        for other in squad.effects:
            if other.effect_id in {source.effect_id,replacement.effect_id,control.effect_id,remover.effect_id}:
                continue
            if other.name in names:
                unsafe=True; break
            if other.parameters.get("target_effect") in names:
                unsafe=True; break
            if any(rule.key in names for rule in other.condition_rules if rule.key):
                unsafe=True; break
            if any(rule.mode is ConditionMode.TARGET_STUNNED for rule in other.condition_rules):
                unsafe=True; break
            if any((rule.event_key or "").startswith("event:state_end:") and (rule.event_key or "").split(":",2)[-1] in names for rule in other.triggers):
                unsafe=True; break
            raw_target=str(other.target or "")
            if any(name in raw_target for name in names):
                unsafe=True; break
        if unsafe:
            continue
        # The omitted control sibling may not be observed indirectly anywhere.
        if any(
            rule.mode is ConditionMode.TARGET_STUNNED
            for effect in squad.effects for rule in effect.condition_rules
        ):
            continue
        rows.append(CertifiedEnemyReplacementLifecycle(
            source.actor,source.effect_id,replacement.effect_id,control.effect_id,
            remover.effect_id,threshold,
        ))
    return tuple(rows)
