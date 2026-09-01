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


def _capability(stat: str, *, ready: bool = True) -> EffectCapability:
    return EffectCapability(
        character="synthetic-reload",
        index=0,
        source="synthetic",
        name="live reload",
        effect_type="buff",
        stat=stat,
        category=EffectCategory.CADENCE_TIMELINE,
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


def _member(
    effect: CompiledEffect,
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
        effects=(effect,),
        skill_levels={},
        favorite_stage=0,
    )


def _squad(effect: CompiledEffect, **member_kwargs) -> CompiledSquad:
    member = _member(effect, **member_kwargs)
    return CompiledSquad((member,), TriggerIndex.from_effects((effect,), actor_count=1))


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
