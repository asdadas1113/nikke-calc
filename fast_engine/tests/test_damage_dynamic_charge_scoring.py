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
from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.targets import compile_target
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule


def _ready_capability(*, stat: str = "charge_speed_pct") -> EffectCapability:
    return EffectCapability(
        character="synthetic-charge",
        index=0,
        source="synthetic",
        name="live charge speed",
        effect_type="buff",
        stat=stat,
        category=EffectCategory.CADENCE_TIMELINE,
        timing_families=("burst",),
        condition_families=(),
        target_family="ally_static",
        advanced_fields=(),
        disposition=CapabilityDisposition.READY,
        blockers=(),
    )


def _charge_speed_effect(*, stat: str = "charge_speed_pct") -> CompiledEffect:
    return CompiledEffect(
        effect_id=0,
        actor=0,
        actor_effect_index=0,
        source="synthetic",
        source_tag="skill",
        name="live charge speed",
        effect_type="buff",
        stat=stat,
        polarity="beneficial",
        target="self",
        target_spec=compile_target(
            "self",
            actor_by_name={"synthetic-charge": 0},
        ),
        conditions=(),
        condition_rules=(),
        triggers=(
            TriggerRule(
                "full_burst_start",
                "full_burst_start",
                TriggerMode.EVENT,
            ),
        ),
        value=50.0,
        duration=1.5,
        max_stack=None,
        max_trigger=None,
        tick_interval=None,
        parameters={},
        capability=_ready_capability(stat=stat),
    )


def _squad(effect: CompiledEffect) -> CompiledSquad:
    member = CompiledCharacter(
        name="synthetic-charge",
        base_atk=1000.0,
        base_def=100.0,
        base_hp=10000.0,
        element=None,
        character_class="화력형",
        squad_group=None,
        burst_stage="3",
        burst_cooldown=40.0,
        burst_regen_time=2.0,
        weapon_type="SR",
        weapon={
            "weapon_type": "SR",
            "fire_mode": "charge",
            "damage_coeff": 100.0,
            "max_ammo": 20,
            "reload_time": 2.0,
            "charge_time": 1.0,
            "full_charge_mult": 100.0,
            "core_dmg_mult": 200.0,
            "post_fire_delay": 0.0,
            "reload_start_delay": 0.0,
            "post_reload_delay": 0.0,
            "is_clip": False,
            "pellets": 1,
            "muzzles": 1,
        },
        effects=(effect,),
        skill_levels={},
        favorite_stage=0,
    )
    return CompiledSquad(
        (member,),
        TriggerIndex.from_effects((effect,), actor_count=1),
    )


def _run_live_speed_case(effect: CompiledEffect) -> tuple[float, float]:
    squad = _squad(effect)
    enemy = EnemyStaticProfile(
        defense=0.0,
        element=None,
        core_uptime=0.0,
        core_px=0.0,
        duration=4.0,
    )
    runtime = BurstRuntime(
        squad,
        BurstPolicy(duration=4.0, first_burst_time=10.0),
        enemy,
    )
    # Activate the finite state directly so this test isolates cadence
    # replanning rather than burst-machine reachability. The effect expires
    # at 1.5 s: 50% speed produces shots at 0.5/1.0, then the in-progress
    # third charge is replanned to 2.0 and normal shots continue at 3.0.
    runtime.dispatcher.effects.activate(
        effect,
        0,
        0.0,
        runtime.scheduler,
    )
    observer = StaticNormalAttackObserver(runtime, duration=4.0)
    if observer.dynamic_charge_actors != (0,):
        raise AssertionError(observer.dynamic_charge_actors)

    result = runtime.run(duration=4.0, score_observer=observer)
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
    return score.char_total[0], per_shot


class DynamicChargeScoringTests(unittest.TestCase):
    def test_live_charge_speed_uses_runtime_shots_without_static_double_count(self):
        effect = _charge_speed_effect()
        squad = _squad(effect)
        self.assertNotIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            static_normal_score_blockers(squad),
        )
        total, per_shot = _run_live_speed_case(effect)
        self.assertAlmostEqual(total, per_shot * 4.0, places=6)

    def test_live_caster_based_charge_speed_uses_same_dynamic_score_bridge(self):
        effect = _charge_speed_effect(stat="charge_speed_caster_based_pct")
        squad = _squad(effect)
        self.assertNotIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_caster_based_pct",
            static_normal_score_blockers(squad),
        )
        # Self-targeting makes caster and target base charge time equal, so 50%
        # caster-based speed is numerically 50% target charge speed here. This
        # specifically locks the caster-based stat routing into the live cadence
        # scorer while the pre-existing ratio arithmetic remains tested by the
        # weapon runtime itself.
        total, per_shot = _run_live_speed_case(effect)
        self.assertAlmostEqual(total, per_shot * 4.0, places=6)

    def test_public_red_hood_glaring_eyes_pair_is_certified(self):
        names = ["라피 : 레드 후드", "레드 후드", "프리카", "민트", "퀀시 : 이스케이프 퀸"]
        squad = compile_moris_squad(build_squad(names))
        blockers = static_normal_score_blockers(squad)
        self.assertFalse(any("레드 후드:글레링 아이즈:charge_speed_pct" in x for x in blockers))
        self.assertFalse(any("레드 후드:글레링 아이즈 2:charge_speed_overflow_conversion_pct" in x for x in blockers))
        self.assertTrue(any("민트:다 함께 불러주세요! 2:max_ammo_pct" in x for x in blockers))

    def test_on_attack_charge_speed_stacks_after_consuming_shot(self):
        base = _charge_speed_effect()
        planned = replace(base.capability, disposition=CapabilityDisposition.PLANNED, blockers=("timing:weapon_hit",))
        effect = replace(
            base,
            value=60.0,
            duration=5.0,
            max_stack=2.0,
            triggers=(TriggerRule("on_attack", "on_attack", TriggerMode.EVENT),),
            capability=planned,
        )
        squad = _squad(effect)
        self.assertFalse(static_normal_score_blockers(squad))
        runtime = BurstRuntime(squad, BurstPolicy(duration=2.1, first_burst_time=10.0), EnemyStaticProfile(defense=0.0, core_uptime=0.0, core_px=0.0, duration=2.1))
        observer = StaticNormalAttackObserver(runtime, duration=2.1)
        # Stop immediately after the first base-speed shot. ActiveEffectStore is
        # not a historical snapshot store, so inspecting 1.01 after advancing to
        # 2.1 would correctly expose later stacks as current state.
        runtime.run(duration=1.01, score_observer=observer)
        self.assertAlmostEqual(runtime.dispatcher.effects.sum_stat(0, "charge_speed_pct", now=1.01), 60.0, places=9)

    def test_charge_speed_overflow_adds_charge_damage_only_above_100(self):
        speed = _charge_speed_effect()
        speed = replace(speed, value=120.0, duration=-1.0, max_stack=None, triggers=(TriggerRule("battle_start", "battle_start", TriggerMode.EVENT),))
        conv_cap = _ready_capability(stat="charge_speed_overflow_conversion_pct")
        conv = replace(
            speed,
            effect_id=1, actor_effect_index=1, name="overflow",
            stat="charge_speed_overflow_conversion_pct", value=240.0, capability=conv_cap,
        )
        member = _squad(speed).members[0]
        member = replace(member, effects=(speed, conv))
        squad = CompiledSquad((member,), TriggerIndex.from_effects((speed, conv), actor_count=1))
        runtime = BurstRuntime(squad, BurstPolicy(duration=1.0, first_burst_time=10.0), EnemyStaticProfile(defense=0.0, core_uptime=0.0, core_px=0.0, duration=1.0))
        runtime.dispatcher.dispatch(__import__('fast_engine.engine.burst', fromlist=['BurstSignal']).BurstSignal(0.0, 'battle_start', 0, 0))
        from fast_engine.engine.damage_state import DamageTermResolver
        terms = DamageTermResolver(squad, runtime.dispatcher.effects, runtime.state, runtime.enemy).resolve(0, now=0.01)
        self.assertAlmostEqual(terms.charge_dmg_pct, 48.0, places=9)

    def test_public_red_wolf_weapon_change_is_explicit_fail_closed(self):
        names=["라피 : 레드 후드","레드 후드","프리카","민트","퀀시 : 이스케이프 퀸"]
        blockers=static_normal_score_blockers(compile_moris_squad(build_squad(names)))
        self.assertTrue(any(x.startswith("weapon_change:레드 후드:레드 울프 무기변경") for x in blockers))

    def test_uncertified_charge_speed_delivery_remains_fail_closed(self):
        effect = _charge_speed_effect()
        planned = replace(
            effect.capability,
            disposition=CapabilityDisposition.PLANNED,
            blockers=("timing:weapon_hit",),
        )
        unsafe = replace(
            effect,
            triggers=(
                TriggerRule("full_charge", "full_charge", TriggerMode.EVENT),
            ),
            capability=planned,
        )
        blockers = static_normal_score_blockers(_squad(unsafe))
        self.assertIn(
            "cadence:synthetic-charge:live charge speed:charge_speed_pct",
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
