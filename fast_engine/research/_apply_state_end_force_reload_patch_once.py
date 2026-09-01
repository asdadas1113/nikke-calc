from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    p.write_text(text.replace(old, new, 1))


# Capability metadata: the stat semantics are implemented, but arbitrary named
# events remain unsupported. Dispatcher has a narrow state_end exception below.
replace_once(
    "fast_engine/engine/capabilities.py",
    '        "reload_speed_pct", "charge_speed_pct", "charge_speed_caster_based_pct",\n',
    '        "reload_speed_pct", "mg_warmup_speed_pct", "force_reload", "charge_speed_pct", "charge_speed_caster_based_pct",\n',
)

# State-end notification gets its own phase: after all ordinary state expiries at
# the same timestamp, before periodic/burst/weapon work, matching Moris tick order.
replace_once(
    "fast_engine/engine/scheduler.py",
    '''    STATE_EXPIRE = 20
    PERIODIC_TICK = 30
''',
    '''    STATE_EXPIRE = 20
    STATE_END_NOTIFY = 21
    PERIODIC_TICK = 30
''',
)
replace_once(
    "fast_engine/engine/scheduler.py",
    '''    EventKind.STATE_EXPIRE: 0,
    EventKind.PERIODIC_TICK: 10,
''',
    '''    EventKind.STATE_EXPIRE: 0,
    EventKind.STATE_END_NOTIFY: 5,
    EventKind.PERIODIC_TICK: 10,
''',
)

# Dispatcher: narrow named-state-end timing exception + force-reload callback.
replace_once(
    "fast_engine/engine/dispatcher.py",
    'from .triggers import TriggerMode\n',
    'from .triggers import TriggerMode\nfrom .scheduler import EventKind\n',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '        "_unsafe_gauge_families", "_strict_score_delivery", "_ammo_charge_sink",\n',
    '        "_unsafe_gauge_families", "_strict_score_delivery", "_ammo_charge_sink",\n        "_force_reload_sink",\n',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''        "reload_speed_pct",
        "mg_warmup_speed_pct",
        "charge_speed_pct",
''',
    '''        "reload_speed_pct",
        "mg_warmup_speed_pct",
        "force_reload",
        "charge_speed_pct",
''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''        self._ammo_charge_sink: Callable[[str, tuple[int, ...], float, float], bool] | None = None
''',
    '''        self._ammo_charge_sink: Callable[[str, tuple[int, ...], float, float], bool] | None = None
        self._force_reload_sink: Callable[[tuple[int, ...], float], bool] | None = None
''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''    def attach_ammo_charge_sink(
        self,
        sink: Callable[[str, tuple[int, ...], float, float], bool],
    ) -> None:
        self._ammo_charge_sink = sink

''',
    '''    def attach_ammo_charge_sink(
        self,
        sink: Callable[[str, tuple[int, ...], float, float], bool],
    ) -> None:
        self._ammo_charge_sink = sink

    def attach_force_reload_sink(
        self,
        sink: Callable[[tuple[int, ...], float], bool],
    ) -> None:
        self._force_reload_sink = sink

''',
)

periodic_helper = '''    @staticmethod
    def _periodic_timing_is_only_blocker(effect: "CompiledEffect") -> bool:
        blockers = effect.capability.blockers
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and bool(blockers)
            and all(blocker == "timing:periodic" for blocker in blockers)
        )

'''
replace_once(
    "fast_engine/engine/dispatcher.py",
    periodic_helper,
    periodic_helper + '''    @staticmethod
    def _state_end_timing_is_only_runtime_blocker(effect: "CompiledEffect") -> bool:
        """Allow only the named-event shape emitted by Fast's timed self-state bridge.

        ``duration_bullets`` remains a runtime safety decision, so its capability
        field blocker may coexist with the state-end timing blocker here.
        """

        blockers = effect.capability.blockers
        allowed = {"timing:named_event", "field:duration_bullets"}
        return (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and bool(blockers)
            and set(blockers).issubset(allowed)
            and any((rule.event_key or "").startswith("event:state_end:") for rule in effect.triggers)
            and all(
                rule.mode is TriggerMode.EVENT
                and (rule.event_key or "").startswith("event:state_end:")
                for rule in effect.triggers
            )
            and not effect.condition_rules
        )

''',
)
replace_once(
    "fast_engine/engine/dispatcher.py",
    '''        capability_ok = (
            effect.capability.disposition is CapabilityDisposition.READY
            or TriggerDispatcher._periodic_timing_is_only_blocker(effect)
        )
''',
    '''        capability_ok = (
            effect.capability.disposition is CapabilityDisposition.READY
            or TriggerDispatcher._periodic_timing_is_only_blocker(effect)
            or TriggerDispatcher._state_end_timing_is_only_runtime_blocker(effect)
        )
''',
)

replace_once(
    "fast_engine/engine/dispatcher.py",
    '''            elif stat in {"ammo_charge_pct", "ammo_charge_flat"}:
                if self._ammo_charge_sink is None or any(target == ENEMY for target in targets):
                    return False
                actor_targets = tuple(int(target) for target in targets)
                if not self._ammo_charge_sink(stat, actor_targets, value, now):
                    return False
            elif stat in self._GAUGE_STATS:
''',
    '''            elif stat in {"ammo_charge_pct", "ammo_charge_flat"}:
                if self._ammo_charge_sink is None or any(target == ENEMY for target in targets):
                    return False
                actor_targets = tuple(int(target) for target in targets)
                if not self._ammo_charge_sink(stat, actor_targets, value, now):
                    return False
            elif stat == "force_reload":
                if self._force_reload_sink is None or any(target == ENEMY for target in targets):
                    return False
                actor_targets = tuple(int(target) for target in targets)
                if not self._force_reload_sink(actor_targets, now):
                    return False
            elif stat in self._GAUGE_STATS:
''',
)

replace_once(
    "fast_engine/engine/dispatcher.py",
    '''    def handle_expiry(self, event) -> None:
        expired = self.effects.handle_expiry(event)
        if expired is None:
            return
        stat = expired.stat or ""
''',
    '''    def handle_expiry(self, event) -> None:
        expired = self.effects.handle_expiry(event)
        if expired is None:
            return

        # Moris removes all timed states first, then emits named state_end events.
        # The first Fast bridge is deliberately restricted to a one-target self
        # buff with an ordinary time lifetime. Group/bullet/removal-driven state
        # endings remain fail-closed until they have their own ordering contract.
        if (
            expired.name
            and expired.effect_type == "buff"
            and expired.target_spec.mode is TargetMode.SELF
            and expired.duration is not None
            and expired.duration >= 0.0
            and expired.parameters.get("duration_bullets") is None
        ):
            self.scheduler.schedule(
                event.time,
                EventKind.STATE_END_NOTIFY,
                actor=expired.actor,
                payload=(expired.actor, expired.name),
            )

        stat = expired.stat or ""
''',
)

# BurstRuntime delivers the phase-5 notification after phase-0 expiries.
replace_once(
    "fast_engine/engine/burst_runtime.py",
    '''            if event.kind is EventKind.PERIODIC_TICK:
''',
    '''            if event.kind is EventKind.STATE_END_NOTIFY:
                from .burst import BurstSignal
                owner, name = event.payload
                self.dispatcher.dispatch(
                    BurstSignal(
                        event.time,
                        f"event:state_end:{name}",
                        int(owner),
                        int(owner),
                    ),
                    context=SignalContext(),
                )
                self.weapons.sync(event.time)
                score_end_of_time(event.time)
                continue

            if event.kind is EventKind.PERIODIC_TICK:
''',
)

# Rapid runtime force reload: Moris ignores the command while already reloading;
# otherwise it zeros ammo and snapshots a normal reload immediately at the event.
insert = '''    def advance_to(self, t: float, *, inclusive: bool = False) -> None:
        for actor in self.actors:
            self._advance_actor_to(actor, t, inclusive=inclusive)

'''
replace_once(
    "fast_engine/engine/dynamic_reload.py",
    insert,
    insert + '''    def apply_force_reload(self, targets: tuple[int, ...], now: float) -> bool:
        selected = tuple(dict.fromkeys(int(actor) for actor in targets))
        if not selected or any(actor not in self.actors for actor in selected):
            return False

        self.advance_to(float(now), inclusive=False)
        for actor in selected:
            st = self._states.get(actor)
            if st is None:
                return False
            if st.phase == "reloading":
                continue
            weapon = self.squad.members[actor].weapon
            factor = self._reload_factor(actor, float(now))
            st.ammo = 0
            st.phase = "reloading"
            st.phase_end = float(now) + (
                float(weapon.get("reload_start_delay", 0.0))
                + float(weapon.get("reload_time", 0.0))
            ) * factor
            self._invalidate(st)
            self._plan(actor, float(now))
            self.state.set_ammo(actor, 0)
        return True

''',
)

replace_once(
    "fast_engine/engine/dynamic_weapon.py",
    '''    def consume_post_shot_bullet_lifetimes(self, actor: int, now: float) -> tuple[int, ...]:
        return self._rapid_reload.consume_post_shot_bullet_lifetimes(actor, now)
''',
    '''    def apply_force_reload(self, targets: tuple[int, ...], now: float) -> bool:
        return self._rapid_reload.apply_force_reload(targets, now)

    def consume_post_shot_bullet_lifetimes(self, actor: int, now: float) -> tuple[int, ...]:
        return self._rapid_reload.consume_post_shot_bullet_lifetimes(actor, now)
''',
)

# Score coverage: force_reload is comparison-critical cadence and state-end
# reload-speed bullet lifetimes can use the already-live recipient shot owner.
replace_once(
    "fast_engine/engine/score.py",
    '''    "mg_warmup_speed_pct",
    "pellet_count",
''',
    '''    "mg_warmup_speed_pct",
    "force_reload",
    "pellet_count",
''',
)

replace_once(
    "fast_engine/engine/score.py",
    '''def _is_dynamic_reload_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in _DYNAMIC_RELOAD_SCORE_STATS:
        return False
    if effect.effect_type != "buff":
        return False
    if effect.parameters.get("duration_bullets") is not None:
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return all(_reload_recipient_score_safe(squad, actor) for actor in targets)
''',
    '''def _valid_dynamic_bullet_lifetime(effect) -> bool:
    bullets = effect.parameters.get("duration_bullets")
    if bullets is None:
        return True
    try:
        value = float(bullets)
    except (TypeError, ValueError):
        return False
    return value >= 1.0 and value.is_integer()


def _is_dynamic_reload_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") not in _DYNAMIC_RELOAD_SCORE_STATS:
        return False
    if effect.effect_type != "buff" or not _valid_dynamic_bullet_lifetime(effect):
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_reload_recipient_score_safe(squad, actor) for actor in targets)
''',
)

marker = '''def _dynamic_reload_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
'''
force_helpers = '''def _is_dynamic_force_reload_score_supported(squad: CompiledSquad, effect) -> bool:
    if (effect.stat or "") != "force_reload" or effect.effect_type != "instant":
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_rapid_actor_score_safe(squad, actor) for actor in targets)


def _dynamic_force_reload_score_actors(squad: CompiledSquad) -> tuple[int, ...]:
    actors: set[int] = set()
    for effect in squad.effects:
        if _is_dynamic_force_reload_score_supported(squad, effect):
            actors.update(_possible_ally_targets(squad, effect))
    return tuple(sorted(actors))


''' + marker
replace_once("fast_engine/engine/score.py", marker, force_helpers)

# The MG patch already adds _dynamic_mg_warmup_score_actors before this return.
replace_once(
    "fast_engine/engine/score.py",
    '''    actors.update(_dynamic_mg_warmup_score_actors(squad))
    return tuple(sorted(actors))
''',
    '''    actors.update(_dynamic_mg_warmup_score_actors(squad))
    actors.update(_dynamic_force_reload_score_actors(squad))
    return tuple(sorted(actors))
''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''            if stat == "mg_warmup_speed_pct" and _is_dynamic_mg_warmup_score_supported(squad, effect):
                continue
            blockers.append(f"cadence:{label}")
''',
    '''            if stat == "mg_warmup_speed_pct" and _is_dynamic_mg_warmup_score_supported(squad, effect):
                continue
            if stat == "force_reload" and _is_dynamic_force_reload_score_supported(squad, effect):
                continue
            blockers.append(f"cadence:{label}")
''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''        runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)
''',
    '''        runtime.dispatcher.attach_ammo_charge_sink(runtime.weapons.apply_ammo_charge)
        runtime.dispatcher.attach_force_reload_sink(runtime.weapons.apply_force_reload)
''',
)

# Regression: timed self state_end -> force reload, then one-shot reload-speed buff.
Path("fast_engine/tests/test_damage_state_end_force_reload.py").write_text(r'''from __future__ import annotations

import unittest

from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition, EffectCapability, EffectCategory
from fast_engine.engine.model import CompiledEffect, CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import StaticNormalAttackObserver, static_normal_score_blockers, static_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule
from fast_engine.tests.test_damage_dynamic_reload_scoring import _member


def _cap(stat: str, *, blockers=()) -> EffectCapability:
    return EffectCapability(
        character="synthetic-reload",
        index=0,
        source="synthetic",
        name=stat,
        effect_type="buff" if stat != "force_reload" else "instant",
        stat=stat,
        category=EffectCategory.CADENCE_TIMELINE,
        timing_families=("named_event",) if blockers else ("lifecycle",),
        condition_families=(),
        target_family="ally_static",
        advanced_fields=("duration_bullets",) if "field:duration_bullets" in blockers else (),
        disposition=CapabilityDisposition.PLANNED if blockers else CapabilityDisposition.READY,
        blockers=tuple(blockers),
    )


def _target():
    return compile_target("self", actor_by_name={"synthetic-reload": 0})


def _provider() -> CompiledEffect:
    return CompiledEffect(
        effect_id=0, actor=0, actor_effect_index=0, source="synthetic", source_tag="skill",
        name="mode", effect_type="buff", stat="reload_speed_pct", polarity="beneficial",
        target="self", target_spec=_target(), conditions=(), condition_rules=(),
        triggers=(TriggerRule("battle_start", "battle_start", TriggerMode.EVENT),),
        value=0.0, duration=1.0, max_stack=None, max_trigger=None, tick_interval=None,
        parameters={}, capability=_cap("reload_speed_pct"),
    )


def _force() -> CompiledEffect:
    return CompiledEffect(
        effect_id=1, actor=0, actor_effect_index=1, source="synthetic", source_tag="skill",
        name="force", effect_type="instant", stat="force_reload", polarity=None,
        target="self", target_spec=_target(), conditions=(), condition_rules=(),
        triggers=(TriggerRule("event:state_end:mode", "event:state_end:mode", TriggerMode.EVENT),),
        value=None, duration=None, max_stack=None, max_trigger=None, tick_interval=None,
        parameters={}, capability=_cap("force_reload", blockers=("timing:named_event",)),
    )


def _one_shot_reload() -> CompiledEffect:
    return CompiledEffect(
        effect_id=2, actor=0, actor_effect_index=2, source="synthetic", source_tag="skill",
        name="one shot reload", effect_type="buff", stat="reload_speed_pct", polarity="beneficial",
        target="self", target_spec=_target(), conditions=(), condition_rules=(),
        triggers=(TriggerRule("event:state_end:mode", "event:state_end:mode", TriggerMode.EVENT),),
        value=50.0, duration=None, max_stack=None, max_trigger=None, tick_interval=None,
        parameters={"duration_bullets": 1},
        capability=_cap("reload_speed_pct", blockers=("timing:named_event", "field:duration_bullets")),
    )


class StateEndForceReloadTests(unittest.TestCase):
    def _squad(self) -> CompiledSquad:
        effects = (_provider(), _force(), _one_shot_reload())
        member = _member(effects, fire_mode="auto", weapon_type="AR")
        weapon = dict(member.weapon)
        weapon.update(max_ammo=10, fire_rate=2.0, reload_time=2.0, reload_start_delay=0.0)
        from dataclasses import replace
        member = replace(member, weapon=weapon)
        return CompiledSquad((member,), TriggerIndex.from_effects(effects, actor_count=1))

    def test_timed_self_state_end_forces_reload_before_one_shot_reload_buff(self):
        squad = self._squad()
        self.assertEqual(static_normal_score_blockers(squad), ())
        duration = 3.1
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=duration, first_burst_time=10.0),
            EnemyStaticProfile(defense=0.0, duration=duration),
        )
        observer = StaticNormalAttackObserver(runtime, duration=duration)
        result = runtime.run(duration=duration, score_observer=observer)
        observer.finish(events_processed=result.events_processed)
        # Shots at 0.0 and 0.5, state expires at 1.0 before the scheduled shot,
        # force_reload starts an unbuffed 2s reload, then the next shot is 3.0.
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.hit_count, 3)
        self.assertFalse(runtime.dispatcher.effects.has_stat(0, "reload_speed_pct", now=3.01))

    def test_asuka_state_end_cadence_bundle_is_certified(self):
        from context.spec import build_squad
        from fast_engine.engine.compiler import compile_moris_squad

        names = ["리틀 머메이드", "델타 : 닌자 시프", "크라운", "아스카 : WILLE", "라피 : 레드 후드"]
        blockers = static_score_blockers(compile_moris_squad(build_squad(names)))
        self.assertNotIn("cadence:아스카 : WILLE:긴급 수복 2:mg_warmup_speed_pct", blockers)
        self.assertNotIn("cadence:아스카 : WILLE:긴급 수복 3:force_reload", blockers)
        self.assertNotIn("cadence:아스카 : WILLE:긴급 수복 5:reload_speed_pct", blockers)


if __name__ == "__main__":
    unittest.main()
''')
