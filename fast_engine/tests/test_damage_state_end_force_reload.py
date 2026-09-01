from __future__ import annotations

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

    def test_unsupported_state_end_provider_keeps_force_reload_blocked(self):
        from dataclasses import replace

        provider = replace(
            _provider(),
            target="all_allies",
            target_spec=compile_target(
                "all_allies",
                actor_by_name={"synthetic-reload": 0},
            ),
        )
        force = _force()
        effects = (provider, force)
        member = _member(effects, fire_mode="auto", weapon_type="AR")
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects(effects, actor_count=1),
        )
        self.assertIn(
            "cadence:synthetic-reload:force:force_reload",
            static_normal_score_blockers(squad),
        )

    def test_force_reload_is_ignored_while_already_reloading(self):
        effects = ()
        member = _member(effects, fire_mode="auto", weapon_type="AR")
        from dataclasses import replace
        weapon = dict(member.weapon)
        weapon.update(max_ammo=1, fire_rate=2.0, reload_time=2.0, reload_start_delay=0.0)
        member = replace(member, weapon=weapon)
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects(effects, actor_count=1),
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=3.0, first_burst_time=10.0),
            EnemyStaticProfile(defense=0.0, duration=3.0),
        )
        runtime.weapons.attach_score_block_sink((0,), lambda _actor, _count, _time: None)
        runtime.start(duration=3.0)
        # First shot at 0.0 leaves reload_wait; advance through the 0.5 reload
        # probe so a 2.0s reload is already fixed to end at 2.5.
        runtime.weapons.advance_to(0.6, inclusive=True)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.phase, "reloading")
        before = st.phase_end
        self.assertTrue(runtime.weapons.apply_force_reload((0,), 1.0))
        self.assertEqual(st.phase, "reloading")
        self.assertEqual(st.phase_end, before)

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
