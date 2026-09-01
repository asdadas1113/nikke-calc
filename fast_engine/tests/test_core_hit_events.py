from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.core_events import (
    expected_core_boundaries_for_blocks,
    is_static_expected_core_count_rule,
    simulate_static_expected_core_boundaries,
)
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.shot_blocks import ShotBlock
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerIndex, compile_trigger_rule


class ExpectedCoreBoundaryTests(unittest.TestCase):
    def test_sg_like_shot_can_cross_multiple_thresholds_without_pellet_events(self):
        boundaries = expected_core_boundaries_for_blocks(
            0,
            (ShotBlock(actor=0, first_time=1.25, count=2, interval=0.5),),
            hits_per_shot=10,
            core_probability=0.5,
            thresholds=(3, 5),
        )
        self.assertEqual(
            [(row.time, row.count_increment) for row in boundaries],
            [
                (1.25, 3),
                (1.25, 2),
                (1.75, 1),
                (1.75, 3),
                (1.75, 1),
            ],
        )

    def test_fractional_probability_places_threshold_on_expected_shot(self):
        boundaries = expected_core_boundaries_for_blocks(
            2,
            (ShotBlock(actor=2, first_time=0.0, count=20, interval=0.1),),
            hits_per_shot=1,
            core_probability=0.25,
            thresholds=(3,),
        )
        self.assertEqual(len(boundaries), 1)
        self.assertAlmostEqual(boundaries[0].time, 1.1, places=12)
        self.assertEqual(boundaries[0].count_increment, 3)

    def test_only_fixed_core_hit_count_spelling_is_certified(self):
        self.assertTrue(
            is_static_expected_core_count_rule(
                compile_trigger_rule("core_hit_count:3")
            )
        )
        self.assertFalse(
            is_static_expected_core_count_rule(
                compile_trigger_rule("core_hit:3")
            )
        )


class ExpectedCoreRuntimeTests(unittest.TestCase):
    NAMES = ["라피", "폴리", "프로덕트 12", "델타", "아니스"]

    @staticmethod
    def _with_core_trigger_damage() -> tuple[CompiledSquad, int]:
        compiled = compile_moris_squad(build_squad(ExpectedCoreRuntimeTests.NAMES))
        owner = compiled.members[0]
        base = next(
            effect for effect in owner.effects
            if effect.effect_type == "damage"
            and effect.target_spec.mode is TargetMode.ENEMY
            and not effect.condition_rules
        )
        core_effect = replace(
            base,
            name="synthetic core-count damage",
            triggers=(compile_trigger_rule("core_hit_count:3"),),
        )
        members = list(compiled.members)
        members[0] = replace(
            owner,
            effects=tuple(
                core_effect if effect.effect_id == base.effect_id else effect
                for effect in owner.effects
            ),
        )
        effects = tuple(effect for member in members for effect in member.effects)
        squad = CompiledSquad(
            tuple(members),
            TriggerIndex.from_effects(effects, actor_count=len(members)),
        )
        return squad, core_effect.effect_id

    def test_runtime_dispatches_only_meaningful_core_count_boundaries(self):
        squad, effect_id = self._with_core_trigger_damage()
        duration = 1.0
        enemy = EnemyStaticProfile(
            duration=duration,
            core_uptime=1.0,
            core_px=1_000_000.0,
        )
        sink = SimpleDamageScoreSink(squad, enemy)
        effect = next(effect for effect in squad.effects if effect.effect_id == effect_id)
        self.assertTrue(sink.supports(effect))

        expected = simulate_static_expected_core_boundaries(
            squad,
            duration=duration,
            core_probability_by_actor={0: 1.0},
            effect_filter=lambda candidate: candidate.effect_id == effect_id,
        )
        expected_count = sum(
            boundary.count_increment
            for boundary in expected
            if boundary.time < duration
        )
        self.assertGreater(expected_count, 0)

        runtime = BurstRuntime(
            squad,
            BurstPolicy(
                duration=duration,
                no_burst_actors=frozenset(range(len(squad.members))),
            ),
            enemy,
            damage_sink=sink,
        )
        runtime.run(duration=duration)

        self.assertEqual(
            runtime.dispatcher._event_counts[(0, "core_hit")],
            expected_count,
        )
        self.assertGreater(sink.char_total[0], 0.0)


if __name__ == "__main__":
    unittest.main()
