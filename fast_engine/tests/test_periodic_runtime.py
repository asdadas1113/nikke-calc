from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition
from fast_engine.engine.compiler import compile_moris_squad


class PeriodicRuntimeTests(unittest.TestCase):
    NAMES = ["밀크", "크라운", "홍련", "앨리스", "나가"]

    def _runtime(self, duration: float) -> BurstRuntime:
        moris_squad = build_squad(self.NAMES)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(
            moris_squad, compiled, {"duration": duration}
        )
        runtime = BurstRuntime(compiled, policy)
        runtime.run(duration=duration)
        return runtime

    @staticmethod
    def _active_atk_effect_names(runtime: BurstRuntime, now: float) -> set[str]:
        return {
            effect.name
            for effect, _active in runtime.dispatcher.effects.iter_stat(
                "atk_pct", now=now
            )
        }

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

    def test_auxiliary_periodic_atk_does_not_overclaim_fast_capability(self):
        moris_squad = build_squad(self.NAMES)
        compiled = compile_moris_squad(moris_squad)
        milk_periodic = next(
            effect
            for effect in compiled.effects
            if effect.name == "밀크에겐 맡겨!"
            and any(rule.is_periodic for rule in effect.triggers)
        )
        # The scheduler/state primitive is usable for Top-ATK selection, but
        # Fast has no damage kernel yet, so atk_pct is not globally READY.
        self.assertEqual(
            milk_periodic.capability.disposition,
            CapabilityDisposition.PLANNED,
        )


if __name__ == "__main__":
    unittest.main()
