from __future__ import annotations

import unittest
from dataclasses import replace

from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import (
    CapabilityDisposition,
    EffectCapability,
    EffectCategory,
)
from fast_engine.engine.model import (
    CompiledCharacter,
    CompiledEffect,
    CompiledSquad,
    EnemyStaticProfile,
)
from fast_engine.engine.normal_attack import expected_normal_block_damage
from fast_engine.engine.score import StaticNormalAttackObserver, static_normal_score_blockers
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule


def _capability(
    stat: str,
    *,
    ready: bool = True,
    category: EffectCategory = EffectCategory.CADENCE_TIMELINE,
) -> EffectCapability:
    return EffectCapability(
        character="synthetic-reload",
        index=0,
        source="synthetic",
        name="live reload",
        effect_type="buff",
        stat=stat,
        category=category,
        timing_families=("burst",),
        condition_families=(),
        target_family="ally_static",
        advanced_fields=(),
        disposition=(
            CapabilityDisposition.READY if ready else CapabilityDisposition.PLANNED
        ),
        blockers=() if ready else ("timing:weapon_hit",),
    )


def _reload_effect(*, duration: float = 1.5, ready: bool = True) -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="live reload",
        effect_type="buff",
        stat="reload_speed_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target(
            "self",
            actor_by_name={"synthetic-reload": 0},
        ),
        conditions=(),
        condition_rules=(),
        triggers=(TriggerRule("full_burst_start", "full_burst_start", TriggerMode.EVENT),),
        value=50.0,
        duration=duration,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_capability("reload_speed_pct", ready=ready),
    )


def _hit_count_effect(*, reducible: bool = True) -> CompiledEffect:
    rule = (
        TriggerRule(
            "hit_count:2",
            "hit_count",
            TriggerMode.MODULO,
            threshold=2.0,
            trigger_count_reducible=True,
        )
        if reducible
        else TriggerRule("hit_count", "hit_count", TriggerMode.EVENT)
    )
    return CompiledEffect(
        effect_id=1,
        actor=0,
        actor_effect_index=1,
        source="synthetic",
        source_tag="skill",
        name="count atk",
        effect_type="buff",
        stat="atk_pct",
        polarity="beneficial",
        target="self",
        target_spec=compile_target(
            "self",
            actor_by_name={"synthetic-reload": 0},
        ),
        conditions=(),
        condition_rules=(),
        triggers=(rule,),
        value=100.0,
        duration=10.0,
        max_stack=2.0,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_capability(
            "atk_pct",
            category=EffectCategory.HIT_FORMULA,
        ),
    )


def _member(
    effects: tuple[CompiledEffect, ...],
    *,
    fire_mode: str = "auto",
    weapon_type: str = "AR",
    is_clip: bool = False,
    post_reload_delay: float = 0.0,
) -> CompiledCharacter:
    weapon = {
        "weapon_type": weapon_type,
        "fire_mode": fire_mode,
        "damage_coeff": 100.0,
        "max_ammo": 2,
        "reload_time": 2.0,
        "fire_rate": 2.0,
        "post_fire_delay": 0.0,
        "reload_start_delay": 0.0,
        "post_reload_delay": post_reload_delay,
        "is_clip": is_clip,
        "pellets": 1,
        "muzzles": 1,
    }
    if fire_mode == "auto_warmup":
        weapon.update(
            fire_rate_max=2.0,
            warmup_bullets=10,
            warmup_cooldown_time=1.0,
        )
    if fire_mode == "charge":
        weapon.update(
            charge_time=1.0,
            full_charge_mult=100.0,
            core_dmg_mult=200.0,
        )
    return CompiledCharacter(
        name="synthetic-reload",
        base_atk=1000.0,
        base_def=100.0,
        base_hp=10000.0,
        element=None,
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type=weapon_type,
        weapon=weapon,
        effects=effects,
        skill_levels={},
        favorite_stage=0,
    )


def _squad(effect: CompiledEffect, **member_kwargs) -> CompiledSquad:
    return _squad_many((effect,), **member_kwargs)


def _squad_many(
    effects: tuple[CompiledEffect, ...],
    **member_kwargs,
) -> CompiledSquad:
    member = _member(effects, **member_kwargs)
    return CompiledSquad((member,), TriggerIndex.from_effects(effects, actor_count=1))


def _run(
    effect: CompiledEffect,
    *,
    duration: float,
    **member_kwargs,
) -> tuple[StaticNormalAttackObserver, float, float]:
    squad = _squad(effect, **member_kwargs)
    enemy = EnemyStaticProfile(
        defense=0.0,
        element=None,
        core_uptime=0.0,
        core_px=0.0,
        duration=duration,
    )
    runtime = BurstRuntime(
        squad,
        BurstPolicy(duration=duration, first_burst_time=10.0),
        enemy,
    )
    runtime.dispatcher.effects.activate(effect, 0, 0.0, runtime.scheduler)
    observer = StaticNormalAttackObserver(runtime, duration=duration)
    result = runtime.run(duration=duration, score_observer=observer)
    score = observer.finish(events_processed=result.events_processed)
    terms = observer.resolver.resolve(0, now=0.25)
    per_shot = expected_normal_block_damage(
        observer.specs[0],
        shot_count=1,
        base_atk=squad.members[0].base_atk,
        enemy_def=enemy.defense,
        terms=terms,
        core_prob=0.0,
        is_full_burst=False,
        is_optimal_range=False,
    )
    return observer, score.char_total[0], per_shot


class DynamicReloadScoringTests(unittest.TestCase):
    def test_auto_reload_duration_is_fixed_at_reload_start(self):
        effect = _reload_effect(duration=1.5)
        self.assertNotIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            static_normal_score_blockers(_squad(effect)),
        )
        observer, total, per_shot = _run(effect, duration=5.5)
        self.assertEqual(observer.dynamic_reload_actors, (0,))
        # Shots: 0.0, 0.5. Reload starts at 1.0 with +50% and therefore ends
        # at 2.0 even though the buff expired at 1.5. Next magazine fires at
        # 2.0, 2.5. Its unbuffed reload runs 3.0 -> 5.0, then one more shot.
        self.assertAlmostEqual(total, per_shot * 5.0, places=6)

    def test_post_reload_delay_uses_state_at_reload_completion(self):
        effect = _reload_effect(duration=1.5)
        observer, total, per_shot = _run(
            effect,
            duration=4.0,
            post_reload_delay=1.0,
        )
        self.assertEqual(observer.dynamic_reload_actors, (0,))
        # The first reload still ends at 2.0, but the buff is already gone at
        # completion, so the 1.0 s post-reload delay is not shortened. Shots are
        # 0.0, 0.5, 3.0, 3.5 inside [0, 4).
        self.assertAlmostEqual(total, per_shot * 4.0, places=6)

    def test_auto_warmup_mode_can_use_compressed_reload_path(self):
        effect = _reload_effect(duration=1.5)
        observer, total, per_shot = _run(
            effect,
            duration=5.5,
            fire_mode="auto_warmup",
            weapon_type="MG",
        )
        self.assertEqual(observer.dynamic_reload_actors, (0,))
        self.assertAlmostEqual(total, per_shot * 5.0, places=6)

    def test_non_clip_charge_reload_reuses_dynamic_charge_runtime(self):
        effect = _reload_effect(duration=2.5)
        observer, total, per_shot = _run(
            effect,
            duration=5.5,
            fire_mode="charge",
            weapon_type="SR",
        )
        self.assertEqual(observer.dynamic_charge_actors, (0,))
        self.assertEqual(observer.dynamic_reload_actors, ())
        # Charge shots at 1.0, 2.0. Reload begins at 2.0 with +50%, remains a
        # one-second reload after expiry at 2.5, then shots at 4.0 and 5.0.
        self.assertAlmostEqual(total, per_shot * 4.0, places=6)

    def test_reducible_hit_count_is_owned_once_by_rapid_runtime(self):
        reload_effect = _reload_effect(duration=10.0)
        count_effect = _hit_count_effect()
        squad = _squad_many((reload_effect, count_effect))
        blockers = static_normal_score_blockers(squad)
        self.assertNotIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            blockers,
        )
        self.assertEqual(blockers, ())

        duration = 2.25
        enemy = EnemyStaticProfile(
            defense=0.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=duration,
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=duration, first_burst_time=10.0),
            enemy,
        )
        runtime.dispatcher.effects.activate(
            reload_effect, 0, 0.0, runtime.scheduler
        )
        observer = StaticNormalAttackObserver(runtime, duration=duration)
        result = runtime.run(duration=duration, score_observer=observer)
        score = observer.finish(events_processed=result.events_processed)

        # Physical shots are 0.0, 0.5, 2.0. hit_count:2 fires post-shot at 0.5,
        # so only the third shot receives +100% ATK. If the old static hit-count
        # planner were still active for this dynamic actor, the same threshold
        # would be dispatched twice and max_stack=2 would make the third shot 3x.
        terms = observer.resolver.resolve(0, now=0.25)
        base = expected_normal_block_damage(
            observer.specs[0],
            shot_count=1,
            base_atk=squad.members[0].base_atk,
            enemy_def=enemy.defense,
            terms=replace(terms, atk_pct=0.0),
            core_prob=0.0,
            is_full_burst=False,
            is_optimal_range=False,
        )
        self.assertAlmostEqual(score.char_total[0], base * 4.0, places=6)

    def test_raw_hit_count_keeps_reload_fail_closed(self):
        reload_effect = _reload_effect(duration=10.0)
        raw_count = _hit_count_effect(reducible=False)
        blockers = static_normal_score_blockers(
            _squad_many((reload_effect, raw_count))
        )
        self.assertIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            blockers,
        )

    def test_clip_reload_remains_fail_closed(self):
        effect = _reload_effect()
        blockers = static_normal_score_blockers(_squad(effect, is_clip=True))
        self.assertIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            blockers,
        )

    def test_uncertified_reload_delivery_remains_fail_closed(self):
        effect = _reload_effect(ready=False)
        blockers = static_normal_score_blockers(_squad(effect))
        self.assertIn(
            "cadence:synthetic-reload:live reload:reload_speed_pct",
            blockers,
        )

    def test_live_max_ammo_refills_new_cap_without_changing_current_magazine(self):
        base=_reload_effect(duration=5.0)
        effect=replace(base,name="live max ammo",stat="max_ammo_pct",value=100.0,capability=_capability("max_ammo_pct"))
        squad=_squad(effect); self.assertEqual(static_normal_score_blockers(squad),())
        runtime=BurstRuntime(squad,BurstPolicy(duration=4.0,first_burst_time=10.0),EnemyStaticProfile(defense=0.0,core_uptime=0.0,core_px=0.0,duration=4.0))
        StaticNormalAttackObserver(runtime,duration=4.0); runtime.start(duration=4.0); rapid=runtime.weapons._rapid_reload
        runtime.weapons.advance_to(0.25,inclusive=True); self.assertEqual(rapid._states[0].ammo,1)
        runtime.dispatcher.effects.activate(effect,0,0.25,runtime.scheduler); runtime.weapons.sync(0.25)
        self.assertEqual(rapid._states[0].ammo,1); self.assertEqual(rapid._full_ammo(0,0.25),4)
        runtime.weapons.advance_to(3.01,inclusive=True); self.assertEqual(rapid._states[0].ammo,3)

    def test_live_max_ammo_expiry_clamps_current_ammo(self):
        base=_reload_effect(duration=0.2)
        effect=replace(base,name="live max ammo",stat="max_ammo_pct",value=200.0,capability=_capability("max_ammo_pct"))
        squad=_squad(effect); runtime=BurstRuntime(squad,BurstPolicy(duration=1.0,first_burst_time=10.0),EnemyStaticProfile(defense=0.0,core_uptime=0.0,core_px=0.0,duration=1.0))
        StaticNormalAttackObserver(runtime,duration=1.0); runtime.start(duration=1.0); rapid=runtime.weapons._rapid_reload
        runtime.dispatcher.effects.activate(effect,0,0.01,runtime.scheduler); runtime.weapons.sync(0.01); rapid._states[0].ammo=5
        self.assertEqual(rapid._full_ammo(0,0.02),6); runtime.weapons.sync(0.25)
        self.assertEqual(rapid._full_ammo(0,0.25),2); self.assertEqual(rapid._states[0].ammo,2)

    def test_reload_time_fixed_is_explicit_cadence_blocker(self):
        base = _reload_effect()
        fixed = replace(
            base,
            stat="reload_time_fixed",
            value=0.5,
            capability=_capability("reload_time_fixed"),
        )
        blockers = static_normal_score_blockers(_squad(fixed))
        self.assertIn(
            "cadence:synthetic-reload:live reload:reload_time_fixed",
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
