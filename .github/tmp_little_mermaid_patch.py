from pathlib import Path


def replace_once(path, old, new, label):
    p=Path(path); text=p.read_text()
    if old not in text: raise SystemExit(f'{label} anchor not found')
    p.write_text(text.replace(old,new,1))


def create_enemy_replacement():
    Path('fast_engine/engine/enemy_replacement.py').write_text(r'''from __future__ import annotations

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
''')


def patch_scheduler():
    replace_once('fast_engine/engine/scheduler.py',
'''    WEAPON_BOUNDARY = 50
    TRIGGER_BOUNDARY = 60
''',
'''    PRE_SHOT_BOUNDARY = 45
    WEAPON_BOUNDARY = 50
    TRIGGER_BOUNDARY = 60
''','scheduler kind')
    replace_once('fast_engine/engine/scheduler.py',
'''    EventKind.RELOAD_DONE: 30,
    EventKind.WEAPON_BOUNDARY: 30,
''',
'''    EventKind.RELOAD_DONE: 30,
    EventKind.PRE_SHOT_BOUNDARY: 30,
    EventKind.WEAPON_BOUNDARY: 30,
''','scheduler phase')
    replace_once('fast_engine/engine/scheduler.py',
'''    sort_key: tuple[float, int, int, int] = field(init=False, repr=False)
''',
'''    sort_key: tuple[float, int, int, int, int] = field(init=False, repr=False)
''','scheduler key type')
    replace_once('fast_engine/engine/scheduler.py',
'''        actor_order = self.actor if self.phase == 30 and self.actor >= 0 else -1
        self.sort_key = (
            float(self.time),
            int(self.phase),
            int(actor_order),
            int(self.sequence),
        )
''',
'''        actor_order = self.actor if self.phase == 30 and self.actor >= 0 else -1
        # A pre-shot boundary must run after earlier roster actors at the same
        # timestamp, but before any ordinary boundary belonging to its own actor.
        actor_subphase = -1 if self.kind is EventKind.PRE_SHOT_BOUNDARY else 0
        self.sort_key = (
            float(self.time),
            int(self.phase),
            int(actor_order),
            int(actor_subphase),
            int(self.sequence),
        )
''','scheduler key')


def patch_dynamic_reload():
    replace_once('fast_engine/engine/dynamic_reload.py',
'''class DynamicRapidBoundary:
    actor: int
    signals: tuple[DynamicRapidCountSignal, ...]
    is_last_bullet: bool = False
''',
'''class DynamicRapidBoundary:
    actor: int
    signals: tuple[DynamicRapidCountSignal, ...]
    is_last_bullet: bool = False
    pre_signals: tuple[DynamicRapidCountSignal, ...] = ()
    score_pending: bool = False
''','rapid boundary')


def patch_dynamic_rapid():
    p=Path('fast_engine/engine/dynamic_rapid.py'); text=p.read_text()
    text=text.replace('from typing import Callable, Sequence\n', 'from dataclasses import dataclass, replace\nfrom typing import Callable, Sequence\n',1)
    text=text.replace('from .dynamic_reload import DynamicRapidReloadRuntime, _RapidActorState\n',
'''from .dynamic_reload import (
    DynamicRapidBoundary,
    DynamicRapidCountSignal,
    DynamicRapidReloadRuntime,
    _RapidActorState,
)
from .scheduler import EventKind, ScheduledEvent
''',1)
    marker='''\n\ndef is_supported_rapid_cover_control(member) -> bool:\n'''
    insert='''\n\n@dataclass(frozen=True, slots=True)
class DynamicSquadAmmoToken:
    generation: int
    actor: int
    expected_hit_count: int
    expected_global_count: int
    count_increment: int


def is_supported_rapid_cover_control(member) -> bool:
'''
    if marker not in text: raise SystemExit('rapid insert marker')
    text=text.replace(marker,insert,1)
    text=text.replace('''    __slots__ = ("_cover_until", "_weapon_block_until")\n''',
'''    __slots__ = (
        "_cover_until", "_weapon_block_until", "_squad_ammo_thresholds",
        "_squad_ammo_generation", "_squad_ammo_scheduled_time",
        "_squad_ammo_dispatched_count",
    )
''',1)
    text=text.replace('''        self._cover_until: dict[int, float] = {}\n        self._weapon_block_until: Callable[[int, float], float | None] | None = None\n''',
'''        self._cover_until: dict[int, float] = {}
        self._weapon_block_until: Callable[[int, float], float | None] | None = None
        self._squad_ammo_thresholds: tuple[int, ...] = ()
        self._squad_ammo_generation = 0
        self._squad_ammo_scheduled_time: float | None = None
        self._squad_ammo_dispatched_count = 0
''',1)
    anchor='''    def attach_score_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, int, float], None],
    ) -> None:
        selected = tuple(sorted(set(int(actor) for actor in actors)))
        # Registration must happen before any duration_bullets activation so the
        # effect store knows not to schedule a stale static Nth-shot expiry.
        self.effects.enable_dynamic_bullet_lifetime_targets(selected)
        super().attach_score_sink(selected, sink)
'''
    addition=anchor+'''\n    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:
        if self._states:
            raise RuntimeError("Fast squad-ammo thresholds must be attached before weapon start")
        values=tuple(sorted({int(value) for value in thresholds if int(value)>0}))
        if values and set(self.actors) != set(range(len(self.squad.members))):
            raise NotImplementedError("Fast squad-ammo first slice requires every squad actor on rapid runtime")
        self._squad_ammo_thresholds=values

    def _next_squad_ammo_target(self, current: int) -> int | None:
        if not self._squad_ammo_thresholds:
            return None
        return min(((current // threshold) + 1) * threshold for threshold in self._squad_ammo_thresholds)

    def _probe_next_physical_shot(self, st: _RapidActorState) -> float | None:
        while st.phase_end <= self.duration + _EPS:
            if self._postpone_firing_for_block(st):
                continue
            if st.phase == "firing":
                return float(st.phase_end)
            self._finish_nonshot_phase(st, float(st.phase_end))
        return None

    def _predict_next_squad_ammo_boundary(self) -> tuple[float, int, int, int] | None:
        if not self._squad_ammo_thresholds or not self.actors:
            return None
        probes={actor: replace(self._states[actor]) for actor in self.actors}
        current=sum(st.hit_count for st in probes.values())
        target=self._next_squad_ammo_target(current)
        if target is None:
            return None
        while current < target:
            candidates=[]
            for actor,st in probes.items():
                when=self._probe_next_physical_shot(st)
                if when is not None:
                    candidates.append((when,actor))
            if not candidates:
                return None
            when,actor=min(candidates)
            if when > self.duration + _EPS:
                return None
            st=probes[actor]
            self._after_shot(st,when)
            current += 1
            if current == target:
                return when,actor,st.hit_count,target
        return None

    def _plan_squad_ammo(self, now: float) -> None:
        if not self._squad_ammo_thresholds or self._squad_ammo_scheduled_time is not None:
            return
        row=self._predict_next_squad_ammo_boundary()
        if row is None:
            return
        when,actor,expected,target=row
        when=max(float(now),float(when))
        if when > self.duration + _EPS:
            return
        increment=target-self._squad_ammo_dispatched_count
        if increment <= 0:
            return
        self._squad_ammo_scheduled_time=when
        self.scheduler.schedule(
            when,EventKind.PRE_SHOT_BOUNDARY,actor=actor,
            payload=DynamicSquadAmmoToken(
                self._squad_ammo_generation,actor,expected,target,increment
            ),
        )

    def refresh_squad_ammo_plan(self, now: float) -> None:
        if not self._squad_ammo_thresholds:
            return
        self._squad_ammo_generation += 1
        self._squad_ammo_scheduled_time=None
        self._plan_squad_ammo(now)
'''
    if anchor not in text: raise SystemExit('rapid attach anchor')
    text=text.replace(anchor,addition,1)
    # Extend begin_full_burst tail.
    old='''            self.state.set_ammo(actor, st.ammo)
            entered.append(actor)
        return tuple(entered)
'''
    new='''            self.state.set_ammo(actor, st.ammo)
            entered.append(actor)
        if entered:
            self.refresh_squad_ammo_plan(now)
        return tuple(entered)

    def start(self, now: float = 0.0) -> None:
        super().start(now)
        self._plan_squad_ammo(now)

    def sync(self, now: float) -> None:
        before=tuple((actor,self._states[actor].generation) for actor in self.actors if actor in self._states)
        super().sync(now)
        after=tuple((actor,self._states[actor].generation) for actor in self.actors if actor in self._states)
        if before != after:
            self.refresh_squad_ammo_plan(now)
        elif self._squad_ammo_scheduled_time is None:
            self._plan_squad_ammo(now)

    def apply_force_reload(self, targets: tuple[int, ...], now: float) -> bool:
        changed=super().apply_force_reload(targets,now)
        if changed:
            self.refresh_squad_ammo_plan(now)
        return changed

    def handle_pre_shot_boundary(self, event: ScheduledEvent) -> DynamicRapidBoundary | None:
        token=event.payload
        if not isinstance(token,DynamicSquadAmmoToken):
            return None
        if token.generation != self._squad_ammo_generation:
            return None
        if self._squad_ammo_scheduled_time is None or abs(self._squad_ammo_scheduled_time-event.time)>1e-7:
            return None

        # Moris weapon actors fire in roster order. Consume same-frame physical
        # shots belonging to earlier actors, but stop immediately before the
        # threshold-crossing actor's own shot.
        for actor in self.actors:
            self._advance_actor_to(
                actor,event.time,inclusive=actor < token.actor
            )
        st=self._states.get(token.actor)
        if st is None or st.phase != "firing" or abs(st.phase_end-event.time)>1e-7:
            self.refresh_squad_ammo_plan(event.time)
            return None
        before=sum(state.hit_count for state in self._states.values())
        if st.hit_count + 1 != token.expected_hit_count or before + 1 != token.expected_global_count:
            self.refresh_squad_ammo_plan(event.time)
            return None

        self._after_shot(st,float(event.time))
        self.state.set_ammo(token.actor,st.ammo)
        self._invalidate(st)  # invalidate any same-shot local token
        self._squad_ammo_scheduled_time=None
        self._squad_ammo_dispatched_count=token.expected_global_count

        signals=[]
        pellet_incs,pellet_last=self._crossing_increments(
            st.dispatched_pellet_count,st.pellet_count,
            self._pellet_thresholds.get(token.actor,()),
        )
        signals.extend(DynamicRapidCountSignal("pellet_hit",inc) for inc in pellet_incs)
        st.dispatched_pellet_count=pellet_last
        hit_incs,hit_last=self._crossing_increments(
            st.dispatched_hit_count,st.hit_count,
            self._hit_thresholds.get(token.actor,()),
        )
        signals.extend(DynamicRapidCountSignal("hit_count",inc) for inc in hit_incs)
        st.dispatched_hit_count=hit_last
        return DynamicRapidBoundary(
            token.actor,tuple(signals),is_last_bullet=st.ammo<=0,
            pre_signals=(DynamicRapidCountSignal("squad_ammo_consume",token.count_increment),),
            score_pending=True,
        )

    def score_pending_shot(self, actor: int, now: float) -> None:
        if self._score_sink is None:
            raise RuntimeError("Fast rapid cadence actor has no score sink")
        self._score_sink(actor,1,float(now))
'''
    if old not in text: raise SystemExit('rapid tail anchor')
    text=text.replace(old,new,1)
    p.write_text(text)


def patch_dynamic_weapon():
    p=Path('fast_engine/engine/dynamic_weapon.py'); text=p.read_text()
    text=text.replace('''class DynamicChargeBoundary:
    actor: int
    signals: tuple[DynamicCountSignal, ...]
    is_last_bullet: bool = False
''',
'''class DynamicChargeBoundary:
    actor: int
    signals: tuple[DynamicCountSignal, ...]
    is_last_bullet: bool = False
    pre_signals: tuple[DynamicCountSignal, ...] = ()
    score_pending: bool = False
''',1)
    anchor='''    def attach_weapon_block_until(
        self, callback: Callable[[int, float], float | None]
    ) -> None:
        self._rapid_reload.attach_weapon_block_until(callback)
'''
    addition=anchor+'''\n    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:
        self._rapid_reload.attach_squad_ammo_thresholds(thresholds)

    def refresh_squad_ammo_plan(self, now: float) -> None:
        self._rapid_reload.refresh_squad_ammo_plan(now)

    def handle_pre_shot_boundary(self, event: ScheduledEvent) -> DynamicChargeBoundary | None:
        row=self._rapid_reload.handle_pre_shot_boundary(event)
        if row is None:
            return None
        return DynamicChargeBoundary(
            row.actor,
            tuple(DynamicCountSignal(x.event_key,x.count_increment) for x in row.signals),
            is_last_bullet=row.is_last_bullet,
            pre_signals=tuple(DynamicCountSignal(x.event_key,x.count_increment) for x in row.pre_signals),
            score_pending=row.score_pending,
        )

    def score_pending_shot(self, actor: int, now: float) -> None:
        self._rapid_reload.score_pending_shot(actor,now)
'''
    if anchor not in text: raise SystemExit('weapon attach anchor')
    text=text.replace(anchor,addition,1)
    # In ammo charge, remember rapid mutation and refresh global plan at end.
    text=text.replace('''        for actor in selected:
            if actor in self._rapid_reload.actors:
''',
'''        rapid_changed = False
        for actor in selected:
            if actor in self._rapid_reload.actors:
                rapid_changed = True
''',1)
    text=text.replace('''            self.state.set_ammo(actor, st.ammo)
        return True

    def apply_force_reload''',
'''            self.state.set_ammo(actor, st.ammo)
        if rapid_changed:
            self._rapid_reload.refresh_squad_ammo_plan(float(now))
        return True

    def apply_force_reload''',1)
    # Preserve new fields when mapping ordinary rapid boundaries.
    text=text.replace('''            return DynamicChargeBoundary(
                rapid.actor,
                tuple(signals),
                is_last_bullet=rapid.is_last_bullet,
            )
''',
'''            return DynamicChargeBoundary(
                rapid.actor,
                tuple(signals),
                is_last_bullet=rapid.is_last_bullet,
                pre_signals=tuple(
                    DynamicCountSignal(row.event_key,row.count_increment)
                    for row in rapid.pre_signals
                ),
                score_pending=rapid.score_pending,
            )
''',1)
    p.write_text(text)


def patch_dispatcher():
    p=Path('fast_engine/engine/dispatcher.py'); text=p.read_text()
    text=text.replace('from .effects import ActiveEffectStore\n',
                      'from .effects import ActiveEffectStore\nfrom .enemy_replacement import certified_enemy_received_damage_replacements\n',1)
    text=text.replace('''        "_control_effect_ids", "_control_remover_ids",
''',
'''        "_control_effect_ids", "_control_remover_ids",
        "_enemy_replacement_lifecycles", "_enemy_replacement_remover_ids",
''',1)
    anchor='''        self._control_remover_ids = frozenset(
            row.remover_effect_id for row in self._control_lifecycles
        )
'''
    addition=anchor+'''        self._enemy_replacement_lifecycles = certified_enemy_received_damage_replacements(squad)
        self._enemy_replacement_remover_ids = frozenset(
            row.remover_effect_id for row in self._enemy_replacement_lifecycles
        )
'''
    if anchor not in text: raise SystemExit('dispatcher init anchor')
    text=text.replace(anchor,addition,1)
    text=text.replace('''        if effect.effect_id in self._control_effect_ids or effect.effect_id in self._control_remover_ids:
            return True
''',
'''        if effect.effect_id in self._control_effect_ids or effect.effect_id in self._control_remover_ids:
            return True
        if effect.effect_id in self._enemy_replacement_remover_ids:
            return True
''',1)
    anchor='''            elif stat == "remove_named_buff" and self._enemy_remove_named_state_runtime_supported(effect):
                name = str(effect.parameters.get("target_effect") or "")
                if tuple(targets) != (ENEMY,):
                    return False
                self.effects.remove_named_state(ENEMY, name, now=now)
'''
    addition='''            elif stat == "remove_named_buff" and effect.effect_id in self._enemy_replacement_remover_ids:
                name = str(effect.parameters.get("target_effect") or "")
                if tuple(targets) != (ENEMY,):
                    return False
                self.effects.remove_named_state(ENEMY, name, now=now)
'''+anchor
    if anchor not in text: raise SystemExit('dispatcher remove anchor')
    text=text.replace(anchor,addition,1)
    p.write_text(text)


def patch_damage_runtime():
    p=Path('fast_engine/engine/damage_runtime.py'); text=p.read_text()
    text=text.replace('''        "_stateful_dot_names", "_weapon_hit_source_ids",
''',
'''        "_stateful_dot_names", "_weapon_hit_source_ids",
        "_certified_squad_ammo_effect_ids",
''',1)
    text=text.replace('''    def __init__(self, squad: "CompiledSquad", enemy: "EnemyStaticProfile") -> None:
''',
'''    def __init__(
        self,
        squad: "CompiledSquad",
        enemy: "EnemyStaticProfile",
        *,
        certified_squad_ammo_effect_ids: frozenset[int] = frozenset(),
    ) -> None:
''',1)
    text=text.replace('''        self._weapon_hit_source_ids: set[int] = set()
''',
'''        self._weapon_hit_source_ids: set[int] = set()
        self._certified_squad_ammo_effect_ids = frozenset(certified_squad_ammo_effect_ids)
''',1)
    anchor='''            if rule.event_key not in _SAFE_EVENT_KEYS:
                key = rule.event_key or ""
'''
    addition='''            if rule.event_key == "squad_ammo_consume":
                if (
                    effect.effect_id not in self._certified_squad_ammo_effect_ids
                    or rule.mode is not TriggerMode.MODULO
                    or int(rule.threshold or 0) <= 0
                ):
                    return False
                continue
            if rule.event_key not in _SAFE_EVENT_KEYS:
                key = rule.event_key or ""
'''
    if anchor not in text: raise SystemExit('damage delivery anchor')
    text=text.replace(anchor,addition,1)
    p.write_text(text)


def patch_score():
    p=Path('fast_engine/engine/score.py'); text=p.read_text()
    text=text.replace('from .effects import ActiveEffectStore\n' if 'from .effects import ActiveEffectStore\n' in text else 'from .dispatcher import TriggerDispatcher\n',
                      ('from .effects import ActiveEffectStore\nfrom .enemy_replacement import certified_enemy_received_damage_replacements\n' if 'from .effects import ActiveEffectStore\n' in text else 'from .dispatcher import TriggerDispatcher\nfrom .enemy_replacement import certified_enemy_received_damage_replacements\n'),1)
    # Add lifecycle skip next to control lifecycle skip.
    anchor='''    if any(
        row.remover_effect_id == effect.effect_id
        and _rapid_actor_score_safe(squad, row.actor)
        for row in certified_stack3_self_stun_remove_lifecycles(squad)
    ):
        return False
'''
    addition=anchor+'''    if any(
        row.remover_effect_id == effect.effect_id
        for row in certified_enemy_received_damage_replacements(squad)
    ):
        return False
'''
    if anchor not in text: raise SystemExit('score remover anchor')
    text=text.replace(anchor,addition,1)
    # Add squad ammo proof after dynamic rapid actor set helper.
    marker='''def _is_score_safe_fixed_periodic(effect) -> bool:
'''
    helper=r'''def _squad_ammo_sequential_damage_score_supported(
    squad: CompiledSquad, effect
) -> bool:
    stat=effect.stat or ""
    if not stat.startswith("sequential_damage:"):
        return False
    suffix=stat.split(":",1)[1]
    if not suffix.isdigit() or int(suffix)<=0:
        return False
    if not (
        effect.effect_type=="damage"
        and effect.target_spec.mode is TargetMode.ENEMY
        and effect.target_spec.runtime_supported
        and effect.value is not None and float(effect.value)>=0.0
        and not effect.parameters
        and not effect.condition_rules
        and len(effect.triggers)==1
    ):
        return False
    rule=effect.triggers[0]
    if not (
        rule.event_key=="squad_ammo_consume"
        and rule.mode is TriggerMode.MODULO
        and not rule.trigger_count_reducible
        and int(rule.threshold or 0)>0
        and abs(float(rule.threshold or 0)-int(rule.threshold or 0))<=1e-9
    ):
        return False
    # First slice is intentionally all-rapid. Requiring every actor to already
    # belong to the score runtime avoids inventing a second cadence model solely
    # for this global counter.
    rapid=set(_dynamic_rapid_reload_score_actors(squad))
    if rapid != set(range(len(squad.members))):
        return False
    for actor,member in enumerate(squad.members):
        if str(member.weapon.get("fire_mode") or "") not in {"auto","auto_warmup"}:
            return False
        if member.weapon.get("is_clip") or member.weapon.get("control"):
            return False
        if not _rapid_actor_score_safe(squad,actor):
            return False
    if any(
        (other.stat or "")=="max_ammo_infinite"
        and any(actor in _possible_ally_targets(squad,other) for actor in range(len(squad.members)))
        for other in squad.effects
    ):
        return False
    if effect.name and any(
        (other.stat or "")=="trigger_count_reduce"
        and other.parameters.get("target_effect")==effect.name
        for other in squad.effects
    ):
        return False
    for other in squad.effects:
        if other.effect_id==effect.effect_id:
            continue
        if not any(rule.event_key=="squad_ammo_consume" for rule in other.triggers):
            continue
        if other.capability.disposition.value != "mirror_moris_nop":
            return False
    return True


def _certified_squad_ammo_effect_ids(squad: CompiledSquad) -> frozenset[int]:
    return frozenset(
        effect.effect_id for effect in squad.effects
        if _squad_ammo_sequential_damage_score_supported(squad,effect)
    )


'''+marker
    if marker not in text: raise SystemExit('score helper marker')
    text=text.replace(marker,helper,1)
    # Two sink constructors.
    old='''    damage_sink = SimpleDamageScoreSink(
        squad, EnemyStaticProfile(defense=0.0, duration=1.0)
    )
'''
    new='''    damage_sink = SimpleDamageScoreSink(
        squad,
        EnemyStaticProfile(defense=0.0, duration=1.0),
        certified_squad_ammo_effect_ids=_certified_squad_ammo_effect_ids(squad),
    )
'''
    if old not in text: raise SystemExit('score compile sink anchor')
    text=text.replace(old,new,1)
    old='''    sink = SimpleDamageScoreSink(squad, enemy_profile)
'''
    new='''    sink = SimpleDamageScoreSink(
        squad,
        enemy_profile,
        certified_squad_ammo_effect_ids=_certified_squad_ammo_effect_ids(squad),
    )
'''
    if old not in text: raise SystemExit('score runtime sink anchor')
    text=text.replace(old,new,1)
    # Attach global threshold after rapid score actors are attached.
    anchor='''        if self.dynamic_reload_actors:
            runtime.weapons.attach_score_block_sink(
                self.dynamic_reload_actors,
                self._score_dynamic_reload_block,
            )
        runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)
'''
    addition='''        if self.dynamic_reload_actors:
            runtime.weapons.attach_score_block_sink(
                self.dynamic_reload_actors,
                self._score_dynamic_reload_block,
            )
        squad_ammo_ids=_certified_squad_ammo_effect_ids(runtime.squad)
        if squad_ammo_ids:
            thresholds=tuple(sorted({
                int(rule.threshold or 0)
                for effect_id in squad_ammo_ids
                for rule in runtime.squad.effects[effect_id].triggers
                if rule.event_key=="squad_ammo_consume"
            }))
            runtime.weapons.attach_squad_ammo_thresholds(thresholds)
        runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)
'''
    if anchor not in text: raise SystemExit('score observer attach anchor')
    text=text.replace(anchor,addition,1)
    p.write_text(text)


def patch_burst_runtime():
    p=Path('fast_engine/engine/burst_runtime.py'); text=p.read_text()
    anchor='''            if event.kind is EventKind.WEAPON_BOUNDARY:
                boundary = self.weapons.handle_boundary(event)
'''
    addition='''            if event.kind is EventKind.PRE_SHOT_BOUNDARY:
                boundary = self.weapons.handle_pre_shot_boundary(event)
                if boundary is not None:
                    from .burst import BurstSignal
                    for pre in boundary.pre_signals:
                        if pre.event_key == "squad_ammo_consume":
                            self.dispatcher.dispatch_team_hit(
                                pre.event_key,
                                time=event.time,
                                attacker=boundary.actor,
                                context=SignalContext(),
                                count_increment=pre.count_increment,
                            )
                        else:
                            self.dispatcher.dispatch(
                                BurstSignal(
                                    event.time,pre.event_key,boundary.actor,boundary.actor,
                                    count_increment=pre.count_increment,
                                ),
                                context=SignalContext(),
                            )
                    if boundary.score_pending:
                        self.weapons.score_pending_shot(boundary.actor,event.time)
                    for count_signal in boundary.signals:
                        self.dispatcher.dispatch(
                            BurstSignal(
                                event.time,count_signal.event_key,boundary.actor,boundary.actor,
                                count_increment=count_signal.count_increment,
                            ),
                            context=SignalContext(),
                        )
                    if boundary.is_last_bullet:
                        self.dispatcher.dispatch(
                            BurstSignal(event.time,"last_bullet",boundary.actor,boundary.actor),
                            context=SignalContext(),
                        )
                    self.weapons.sync(event.time)
                score_end_of_time(event.time)
                continue

            if event.kind is EventKind.WEAPON_BOUNDARY:
                boundary = self.weapons.handle_boundary(event)
'''
    if anchor not in text: raise SystemExit('burst pre-shot anchor')
    text=text.replace(anchor,addition,1)
    p.write_text(text)


def create_tests():
    Path('fast_engine/tests/test_damage_little_mermaid_lifecycle.py').write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.enemy_replacement import certified_enemy_received_damage_replacements
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import (
    StaticNormalAttackObserver,
    _certified_squad_ammo_effect_ids,
    score_static_squad,
    static_score_blockers,
)
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.triggers import TriggerIndex


class LittleMermaidLifecycleTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        moris=spec.build_squad(list(snapshot.SQUADS['레이드_델타']['members']))
        squad=compile_moris_squad(moris)
        actor=next(i for i,m in enumerate(squad.members) if m.name=='리틀 머메이드')
        by_name={e.name:e for e in squad.members[actor].effects if e.name}
        return moris,squad,actor,by_name

    @staticmethod
    def _replace_effect(squad,effect_id,new_effect):
        members=list(squad.members)
        owner=squad.effects[effect_id].actor
        members[owner]=replace(
            members[owner],
            effects=tuple(new_effect if e.effect_id==effect_id else e for e in members[owner].effects),
        )
        effects=tuple(e for m in members for e in m.effects)
        return CompiledSquad(tuple(members),TriggerIndex.from_effects(effects,actor_count=len(members)))

    def test_public_delta_has_no_blockers_and_exact_owned_ids(self):
        _moris,squad,actor,by_name=self._fixture()
        self.assertEqual(static_score_blockers(squad),())
        rows=certified_enemy_received_damage_replacements(squad)
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row.actor,actor)
        self.assertEqual(row.source_effect_id,by_name['거품'].effect_id)
        self.assertEqual(row.replacement_effect_id,by_name['터진 거품'].effect_id)
        self.assertEqual(row.remover_effect_id,by_name['터진 거품 3'].effect_id)
        self.assertEqual(row.threshold,50)
        self.assertEqual(_certified_squad_ammo_effect_ids(squad),frozenset({by_name['거품 난사'].effect_id}))

    def test_moris_and_fast_replace_source_at_fiftieth_hit(self):
        moris,squad,_actor,by_name=self._fixture()
        result=simulate(moris,config={'duration':3.0,'rng_mode':'expected'},verbose=True)
        moris_new=[float(x.t) for x in result.log.buff_events if x.name=='터진 거품' and x.kind=='activate']
        moris_old_end=[float(x.t) for x in result.log.buff_events if x.name=='거품' and x.kind=='expire']
        self.assertEqual(len(moris_new),1); self.assertEqual(len(moris_old_end),1)

        fast_new=[]; fast_remove=[]
        orig_activate=ActiveEffectStore.activate_group
        orig_remove=ActiveEffectStore.remove_named_state
        def traced_activate(store,effect,targets,now,scheduler):
            out=orig_activate(store,effect,targets,now,scheduler)
            if effect.effect_id==by_name['터진 거품'].effect_id and out:
                fast_new.append(float(now))
            return out
        def traced_remove(store,target,name,*,now):
            out=orig_remove(store,target,name,now=now)
            if name=='거품' and out:
                fast_remove.append(float(now))
            return out
        policy=compile_burst_policy(moris,squad,{'duration':3.0,'rng_mode':'expected'})
        with patch.object(ActiveEffectStore,'activate_group',new=traced_activate), patch.object(ActiveEffectStore,'remove_named_state',new=traced_remove):
            score_static_squad(squad,policy,EnemyStaticProfile(duration=3.0,core_px=0.0),duration=3.0)
        self.assertEqual(len(fast_new),1); self.assertEqual(len(fast_remove),1)
        self.assertAlmostEqual(fast_new[0],moris_new[0],places=9)
        self.assertAlmostEqual(fast_remove[0],moris_old_end[0],places=9)
        self.assertAlmostEqual(fast_new[0],2.05,places=9)

    def test_global_500_crossing_matches_moris_and_is_pre_normal_shot(self):
        moris,squad,_actor,by_name=self._fixture()
        policy=compile_burst_policy(moris,squad,{'duration':8.1,'rng_mode':'expected'})
        crossings=[]; order=[]
        orig_team=TriggerDispatcher.dispatch_team_hit
        orig_activate=SimpleDamageScoreSink.activate
        orig_score=StaticNormalAttackObserver._score_dynamic_reload_block
        def traced_team(dispatcher,event_key,**kwargs):
            if event_key=='squad_ammo_consume': crossings.append(float(kwargs['time']))
            return orig_team(dispatcher,event_key,**kwargs)
        def traced_activate(sink,effect,**kwargs):
            if effect.effect_id==by_name['거품 난사'].effect_id:
                order.append(('skill',float(kwargs['now'])))
            return orig_activate(sink,effect,**kwargs)
        def traced_score(observer,actor,count,time):
            if crossings and abs(float(time)-crossings[-1])<1e-9 and count==1:
                order.append(('normal',float(time)))
            return orig_score(observer,actor,count,time)
        with patch.object(TriggerDispatcher,'dispatch_team_hit',new=traced_team), patch.object(SimpleDamageScoreSink,'activate',new=traced_activate), patch.object(StaticNormalAttackObserver,'_score_dynamic_reload_block',new=traced_score):
            fast=score_static_squad(squad,policy,EnemyStaticProfile(duration=8.1,core_px=0.0),duration=8.1)
        self.assertEqual(len(crossings),3)
        expected=(4.133333333333324,6.033333333333317,7.93333333333331)
        for actual,want in zip(crossings,expected): self.assertAlmostEqual(actual,want,places=9)
        first=[kind for kind,t in order if abs(t-crossings[0])<1e-9]
        self.assertGreaterEqual(len(first),2)
        self.assertEqual(first[:2],['skill','normal'])
        self.assertLess(fast.events_processed,500)

    def test_sequential_damage_keeps_exact_ten_hit_spec(self):
        _moris,squad,_actor,by_name=self._fixture()
        ids=_certified_squad_ammo_effect_ids(squad)
        sink=SimpleDamageScoreSink(
            squad,EnemyStaticProfile(duration=1.0),
            certified_squad_ammo_effect_ids=ids,
        )
        effect=by_name['거품 난사']
        self.assertTrue(sink.supports(effect))
        self.assertEqual(sink.specs[effect.effect_id].hit_count,10)

    def test_neighboring_replacement_shapes_fail_closed(self):
        _moris,squad,_actor,by_name=self._fixture()
        replacement=by_name['터진 거품']
        bad=self._replace_effect(squad,replacement.effect_id,replace(replacement,value=float(replacement.value)+1.0))
        self.assertFalse(certified_enemy_received_damage_replacements(bad))
        self.assertIn('normal_state:리틀 머메이드:터진 거품 3:remove_named_buff',static_score_blockers(bad))

        remover=by_name['터진 거품 3']
        bad2=self._replace_effect(squad,remover.effect_id,replace(remover,parameters={'target_effect':'터진 거품'}))
        self.assertFalse(certified_enemy_received_damage_replacements(bad2))

    def test_wider_squad_ammo_family_stays_closed(self):
        _moris,squad,_actor,by_name=self._fixture()
        barrage=by_name['거품 난사']
        extra=by_name['세이렌 송']
        # A second non-NOP squad-ammo consumer invalidates the narrow ownership proof.
        rule=replace(barrage.triggers[0],threshold=250.0,raw='squad_ammo_consume:250')
        widened=replace(extra,triggers=(rule,))
        bad=self._replace_effect(squad,extra.effect_id,widened)
        self.assertFalse(_certified_squad_ammo_effect_ids(bad))
        self.assertIn('skill_damage:리틀 머메이드:거품 난사:sequential_damage:10',static_score_blockers(bad))


if __name__=='__main__':
    unittest.main()
''')


create_enemy_replacement()
patch_scheduler()
patch_dynamic_reload()
patch_dynamic_rapid()
patch_dynamic_weapon()
patch_dispatcher()
patch_damage_runtime()
patch_score()
patch_burst_runtime()
create_tests()
