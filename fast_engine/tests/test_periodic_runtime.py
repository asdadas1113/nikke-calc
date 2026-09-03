from __future__ import annotations

import unittest
from unittest.mock import patch

from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.capabilities import CapabilityDisposition
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.frame_lattice import moris_observed_tick
from fast_engine.engine.weapon import DynamicChargeCadenceRuntime

FRAME = 1.0 / 60.0


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

    @staticmethod
    def _milk_active_cohorts(runtime: BurstRuntime, now: float) -> set[tuple[int, ...]]:
        # ActiveEffectStore stores one row per target while keeping the whole
        # activation cohort on every row. Deduplicate cohorts before asserting
        # activation count/target count.
        return {
            active.cohort
            for effect, active in runtime.dispatcher.effects.iter_stat("atk_pct", now=now)
            if effect.name == "밀크에겐 맡겨!"
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

        base_cohorts = self._milk_active_cohorts(base, 20.1)
        favorite_cohorts = self._milk_active_cohorts(favorite, 20.1)

        self.assertEqual(len(base_cohorts), 1)
        self.assertEqual(len(favorite_cohorts), 1)
        self.assertEqual(len(next(iter(base_cohorts))), 2)
        self.assertEqual(len(next(iter(favorite_cohorts))), 3)

    def test_milk_individual_full_charge_times_fit_moris_frame_polling_envelope(self):
        """Continuous Fast cadence may lead frame-stepped Moris by accumulated polls.

        Moris checks charge completion and post-fire completion only on 1/60 s
        ticks. Fast intentionally resolves those boundaries continuously. The first
        shot has no accumulated post-fire polling and should coincide; after that,
        each completed shot may add at most roughly one frame of phase-polling
        difference. This test guards semantics without reintroducing a frame loop.
        """
        duration = 30.0
        moris_squad, compiled = self._compiled(favorite_stage=3)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": duration})

        fast_shots: list[float] = []
        original_dispatch = TriggerDispatcher.dispatch
        original_boundary = DynamicChargeCadenceRuntime._shot_is_boundary

        def every_milk_shot_is_boundary(runtime, actor, absolute_count):
            if actor == 0:
                return True
            return original_boundary(runtime, actor, absolute_count)

        def traced_dispatch(dispatcher, signal, *args, **kwargs):
            if signal.owner_actor == 0 and signal.event_key == "full_charge_hit":
                increment = int(getattr(signal, "count_increment", 1))
                fast_shots.extend([signal.time] * increment)
            return original_dispatch(dispatcher, signal, *args, **kwargs)

        with (
            patch.object(
                DynamicChargeCadenceRuntime,
                "_shot_is_boundary",
                new=every_milk_shot_is_boundary,
            ),
            patch.object(TriggerDispatcher, "dispatch", new=traced_dispatch),
        ):
            BurstRuntime(compiled, policy).run(duration=duration)

        moris = simulate(
            moris_squad,
            config={"duration": duration, "rng_mode": "expected"},
            verbose=True,
        )
        moris_shots = [
            ev.t
            for ev in moris.hits
            if ev.caster == "밀크" and "full_charge_hit" in ev.hit_tag
        ]

        pairs = list(zip(fast_shots[:20], moris_shots[:20]))
        self.assertGreaterEqual(len(pairs), 10)
        self.assertAlmostEqual(pairs[0][0], pairs[0][1], places=9)
        for shot_no, (fast_t, moris_t) in enumerate(pairs, start=1):
            self.assertLessEqual(
                abs(fast_t - moris_t),
                shot_no * FRAME + 1e-8,
                f"shot={shot_no}, fast={fast_t:.6f}, moris={moris_t:.6f}, delta={fast_t-moris_t:+.6f}",
            )

    def test_milk_every_tenth_full_charge_boundary_fits_polling_envelope(self):
        duration = 80.0
        moris_squad, compiled = self._compiled(favorite_stage=3)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": duration})

        fast_boundaries: list[tuple[float, int]] = []
        original_dispatch = TriggerDispatcher.dispatch

        def traced_dispatch(dispatcher, signal, *args, **kwargs):
            if signal.owner_actor == 0 and signal.event_key == "full_charge_hit":
                fast_boundaries.append(
                    (signal.time, int(getattr(signal, "count_increment", 1)))
                )
            return original_dispatch(dispatcher, signal, *args, **kwargs)

        with patch.object(TriggerDispatcher, "dispatch", new=traced_dispatch):
            BurstRuntime(compiled, policy).run(duration=duration)

        moris = simulate(
            moris_squad,
            config={"duration": duration, "rng_mode": "expected"},
            verbose=True,
        )
        moris_full_charge = [
            ev.t
            for ev in moris.hits
            if ev.caster == "밀크" and "full_charge_hit" in ev.hit_tag
        ]
        moris_tenth = moris_full_charge[9::10]
        fast_tenth = [time for time, increment in fast_boundaries if increment >= 10]

        self.assertTrue(fast_tenth, fast_boundaries)
        self.assertTrue(moris_tenth, moris_full_charge)
        pairs = list(zip(fast_tenth, moris_tenth))
        for boundary_no, (fast_t, moris_t) in enumerate(pairs, start=1):
            shot_no = boundary_no * 10
            self.assertLessEqual(
                abs(fast_t - moris_t),
                shot_no * FRAME + 1e-8,
                f"boundary={boundary_no}, fast={fast_t:.6f}, moris={moris_t:.6f}, delta={fast_t-moris_t:+.6f}",
            )

    def test_milk_periodic_cadence_preserves_moris_burst_cycle_count_and_timing(self):
        duration = 80.0
        moris_squad, compiled = self._compiled(favorite_stage=3)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": duration})
        fast = BurstRuntime(compiled, policy).run(duration=duration)

        moris = simulate(
            moris_squad,
            config={"duration": duration, "rng_mode": "expected"},
            verbose=True,
        )
        moris_starts = [
            row.t for row in moris.log.burst_log if row.event == "full_burst 시작"
        ]

        # The Fast runtime is continuous-time; Moris' 1/60 frame polling can move
        # the 10th-full-charge CDR boundary by several accumulated frames. Keep
        # the same number of cycles and a tight sub-0.2 s timing envelope instead
        # of forcing Fast to emulate Moris' global frame loop.
        self.assertEqual(len(fast.full_burst_starts), len(moris_starts))
        self.assertGreaterEqual(len(moris_starts), 5)
        for cycle, (actual, expected) in enumerate(
            zip(fast.full_burst_starts, moris_starts), start=1
        ):
            self.assertLessEqual(
                abs(actual - expected),
                12 * FRAME + 1e-8,
                f"cycle={cycle}, fast={actual:.6f}, moris={expected:.6f}, delta={actual-expected:+.6f}",
            )

    def test_periodic_deadlines_use_nominal_moris_outer_ticks_without_drift(self):
        duration = 70.0
        moris_squad, compiled = self._compiled(favorite_stage=3)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": duration})
        target = self._milk_periodic(compiled)
        seen: list[float] = []
        original = TriggerDispatcher.dispatch_periodic

        def traced(dispatcher, effect_id, rule_index, *, time, context):
            if effect_id == target.effect_id:
                seen.append(time)
            return original(
                dispatcher, effect_id, rule_index, time=time, context=context
            )

        with patch.object(TriggerDispatcher, "dispatch_periodic", new=traced):
            BurstRuntime(compiled, policy).run(duration=duration)

        expected = [
            moris_observed_tick(nominal, horizon=duration)
            for nominal in (20.0, 40.0, 60.0)
        ]
        self.assertEqual(seen, expected)

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
