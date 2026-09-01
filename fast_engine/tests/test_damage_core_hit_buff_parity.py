from __future__ import annotations

import copy
import unittest

import calculator.buff_manager as moris_buff_manager
from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.core_events import simulate_static_expected_core_boundaries
from fast_engine.engine.model import EnemyStaticProfile


class WinterGuillotineCoreHitBuffParityTests(unittest.TestCase):
    NAME = "길로틴 : 윈터 슬레이어"
    EFFECT_NAME = "경험치"
    DURATION = 5.0

    def _simulate_moris_with_core_count_alias(self, moris_squad):
        """Alias only the current Moris spelling gap at the test boundary."""
        original = moris_buff_manager._PARSED_SKILLS[self.NAME]
        aliased = copy.deepcopy(original)
        changed = 0
        for candidate in aliased:
            if candidate.get("name") != self.EFFECT_NAME:
                continue
            timings = candidate.get("trigger", {}).get("timing", [])
            if timings == ["core_hit_count:3"]:
                candidate["trigger"]["timing"] = ["core_hit:3"]
                changed += 1
        self.assertEqual(changed, 1)

        moris_buff_manager._PARSED_SKILLS[self.NAME] = aliased
        try:
            return simulate(
                moris_squad,
                config={
                    "duration": self.DURATION,
                    "rng_mode": "expected",
                    "first_burst_time": self.DURATION,
                    "max_burst_count": 0,
                },
                enemy={
                    "def": 31784,
                    "code": None,
                    "core_px": 1_000_000.0,
                    "has_parts": False,
                    "optimal_range_weapons": [],
                    "immune_windows": [],
                    "element_windows": [],
                },
                verbose=True,
            )
        finally:
            moris_buff_manager._PARSED_SKILLS[self.NAME] = original

    def test_first_real_core_hit_count_buff_matches_intended_moris_semantics(self):
        moris_squad = build_squad([self.NAME])
        compiled = compile_moris_squad(moris_squad, require_five=False)
        actor = 0
        effect = next(
            candidate
            for candidate in compiled.members[actor].effects
            if candidate.name == self.EFFECT_NAME
            and [rule.raw for rule in candidate.triggers] == ["core_hit_count:3"]
        )
        self.assertEqual(effect.effect_type, "buff")
        self.assertEqual(effect.stat, "atk_pct")
        self.assertEqual(effect.max_stack, 100.0)

        enemy = EnemyStaticProfile(
            duration=self.DURATION,
            core_uptime=1.0,
            core_px=1_000_000.0,
        )
        runtime = BurstRuntime(
            compiled,
            BurstPolicy(
                duration=self.DURATION,
                first_burst_time=self.DURATION,
                max_burst_count=0,
                no_burst_actors=frozenset({actor}),
            ),
            enemy,
        )
        runtime._broadcast(0.0, "battle_start")

        boundaries = simulate_static_expected_core_boundaries(
            compiled,
            duration=self.DURATION,
            core_probability_by_actor={actor: 1.0},
            effect_filter=lambda candidate: candidate.effect_id == effect.effect_id,
        )
        self.assertGreaterEqual(len(boundaries), 1)
        first = boundaries[0]
        self.assertEqual(first.count_increment, 3)

        result = runtime.dispatcher.dispatch(
            BurstSignal(
                first.time,
                "core_hit",
                actor,
                actor,
                count_increment=first.count_increment,
            )
        )
        self.assertIn(effect.effect_id, result.activated_effect_ids)
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(
                actor,
                self.EFFECT_NAME,
                now=first.time,
            ),
            1.0,
        )
        fast_atk_pct = runtime.dispatcher.effects.sum_stat(
            actor,
            "atk_pct",
            now=first.time,
        )
        self.assertAlmostEqual(fast_atk_pct, float(effect.value or 0.0), places=12)

        authority = self._simulate_moris_with_core_count_alias(moris_squad)
        moris_events = [
            event
            for event in authority.log.buff_events
            if event.kind == "activate"
            and event.name == self.EFFECT_NAME
            and event.stat == "atk_pct"
        ]
        self.assertGreaterEqual(len(moris_events), 1)
        first_moris = moris_events[0]

        self.assertAlmostEqual(first.time, first_moris.t, delta=(1.0 / 60.0) + 1e-9)
        self.assertEqual(first_moris.stack, 1)
        self.assertAlmostEqual(fast_atk_pct, float(first_moris.value or 0.0), places=12)


if __name__ == "__main__":
    unittest.main()
