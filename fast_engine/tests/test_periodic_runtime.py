from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition
from fast_engine.engine.compiler import compile_moris_squad


class PeriodicRuntimeTests(unittest.TestCase):
    NAMES = ["밀크", "크라운", "홍련", "앨리스", "나가"]

    def _compiled(self, *, favorite_stage: int = 3):
        moris_squad = build_squad(
            self.NAMES,
            chars={"밀크": {"favorite_stage": favorite_stage}},
        )
        return moris_squad, compile_moris_squad(moris_squad)

    def _runtime(self, duration: float, *, favorite_stage: int = 3) -> BurstRuntime:
        moris_squad, compiled = self._compiled(favorite_stage=favorite_stage)
        policy = compile_burst_policy(
            moris_squad, compiled, {"duration": duration}
        )
        runtime = BurstRuntime(compiled, policy)
        runtime.run(duration=duration)
        return runtime

    @staticmethod
    def _milk_periodic(compiled):
        rows = [
            effect
            for effect in compiled.effects
            if effect.name == "밀크에겐 맡겨!"
            and any(rule.is_periodic for rule in effect.triggers)
        ]
        if len(rows) != 1:
            raise AssertionError(f"expected one active Milk periodic variant, got {len(rows)}")
        return rows[0]

    @staticmethod
    def _active_atk_effect_names(runtime: BurstRuntime, now: float) -> set[str]:
        return {
            effect.name
            for effect, _active in runtime.dispatcher.effects.iter_stat(
                "atk_pct", now=now
            )
        }

    def test_milk_favorite_stage_selects_one_periodic_target_variant(self):
        _s0, compiled0 = self._compiled(favorite_stage=0)
        _s1, compiled1 = self._compiled(favorite_stage=1)
        _s3, compiled3 = self._compiled(favorite_stage=3)

        self.assertEqual(self._milk_periodic(compiled0).target, "allies_top_atk:2")
        self.assertEqual(self._milk_periodic(compiled1).target, "allies_top_atk:3")
        # Later favorite stages replace other skill slots; S1 must remain the
        # stage-1 favorite variant rather than falling back to base S1.
        self.assertEqual(self._milk_periodic(compiled3).target, "allies_top_atk:3")

    def test_every_20s_first_fires_at_20_not_battle_start(self):
        before = self._runtime(19.9)
        self.assertNotIn(
            "밀크에겐 맡겨!",
            self._active_atk_effect_names(before, 19.9),
        )

        after = self._runtime(20.1)
        self.assertIn(
            "밀크에겐 맡겨!",
            self._active_atk_effect_names(after, 20.1),
        )

    def test_periodic_activation_uses_active_favorite_target_count(self):
        base = self._runtime(20.1, favorite_stage=0)
        favorite = self._runtime(20.1, favorite_stage=3)

        base_cohorts = [
            active.cohort
            for effect, active in base.dispatcher.effects.iter_stat("atk_pct", now=20.1)
            if effect.name == "밀크에겐 맡겨!"
        ]
        favorite_cohorts = [
            active.cohort
            for effect, active in favorite.dispatcher.effects.iter_stat("atk_pct", now=20.1)
            if effect.name == "밀크에겐 맡겨!"
        ]
        self.assertEqual([len(cohort) for cohort in base_cohorts], [2])
        self.assertEqual([len(cohort) for cohort in favorite_cohorts], [3])

    def test_auxiliary_periodic_atk_does_not_overclaim_fast_capability(self):
        _squad, compiled = self._compiled()
        milk_periodic = self._milk_periodic(compiled)
        # The scheduler/state primitive is usable for Top-ATK selection, but
        # Fast has no damage kernel yet, so atk_pct is not globally READY.
        self.assertEqual(
            milk_periodic.capability.disposition,
            CapabilityDisposition.PLANNED,
        )


if __name__ == "__main__":
    unittest.main()
