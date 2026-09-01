from __future__ import annotations

import unittest

from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.core_events import simulate_static_expected_core_boundaries
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile


class _TrackingDamageSink(SimpleDamageScoreSink):
    __slots__ = ("effect_events",)

    def __init__(self, squad, enemy) -> None:
        super().__init__(squad, enemy)
        self.effect_events: list[tuple[int, float, float]] = []

    def _score_spec(self, effect_id: int, *, now: float, full_burst: bool) -> bool:
        actor = self._effect_actor.get(effect_id)
        before = None if actor is None else self.char_total[actor]
        fired = super()._score_spec(
            effect_id,
            now=now,
            full_burst=full_burst,
        )
        if fired and actor is not None and before is not None:
            self.effect_events.append(
                (effect_id, now, self.char_total[actor] - before)
            )
        return fired


class WinterLudmillaCoreHitParityTests(unittest.TestCase):
    NAME = "루드밀라 : 윈터 오너"
    EFFECT_NAME = "눈보라"
    DURATION = 10.0

    def test_first_real_core_hit_count_damage_matches_moris(self):
        """Certify the first real parsed core-count activation end to end.

        Winter Ludmilla also refills ammo on ``hit_count:60``. Moris notifies
        ``core_hit`` inside the physical-hit loop before the shot-level hit-count
        notification, so the first Snowstorm activation is still a static-cadence
        boundary. Later Snowstorm activations are intentionally outside this test:
        after that same shot the ammo refill can change future cadence and requires
        dynamic core-boundary replanning rather than a static schedule.
        """

        moris_squad = build_squad([self.NAME])
        compiled = compile_moris_squad(moris_squad, require_five=False)
        actor = 0
        effect = next(
            candidate
            for candidate in compiled.members[actor].effects
            if candidate.name == self.EFFECT_NAME
        )
        self.assertEqual(effect.effect_type, "damage")
        self.assertEqual(effect.stat, "bonus_damage")
        self.assertEqual(
            [rule.raw for rule in effect.triggers],
            ["core_hit_count:60"],
        )

        enemy = EnemyStaticProfile(
            duration=self.DURATION,
            core_uptime=1.0,
            core_px=1_000_000.0,
        )
        sink = _TrackingDamageSink(compiled, enemy)
        self.assertTrue(sink.supports(effect))

        runtime = BurstRuntime(
            compiled,
            BurstPolicy(
                duration=self.DURATION,
                first_burst_time=self.DURATION,
                max_burst_count=0,
                no_burst_actors=frozenset({actor}),
            ),
            enemy,
            damage_sink=sink,
        )
        # Activate permanent battle-start state without asking BurstRuntime to
        # reserve all future core boundaries; the latter is deliberately guarded
        # until dynamic ammo/cadence replanning is implemented.
        runtime._broadcast(0.0, "battle_start")

        boundaries = simulate_static_expected_core_boundaries(
            compiled,
            duration=self.DURATION,
            core_probability_by_actor={actor: 1.0},
            effect_filter=lambda candidate: candidate.effect_id == effect.effect_id,
        )
        self.assertGreaterEqual(len(boundaries), 1)
        first = boundaries[0]
        self.assertEqual(first.actor, actor)
        self.assertEqual(first.event_key, "core_hit")
        self.assertEqual(first.count_increment, 60)

        runtime.dispatcher.dispatch(
            BurstSignal(
                first.time,
                "core_hit",
                actor,
                actor,
                count_increment=first.count_increment,
            )
        )
        fast_events = [
            row for row in sink.effect_events if row[0] == effect.effect_id
        ]
        self.assertEqual(len(fast_events), 1)
        _, fast_time, fast_damage = fast_events[0]

        config = {
            "duration": self.DURATION,
            "rng_mode": "expected",
            "first_burst_time": self.DURATION,
            "max_burst_count": 0,
        }
        authority = simulate(
            moris_squad,
            config=config,
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
        moris_hits = [
            hit
            for hit in authority.hits
            if hit.caster == self.NAME and hit.skill_name == self.EFFECT_NAME
        ]
        self.assertGreaterEqual(len(moris_hits), 1)
        first_moris = moris_hits[0]

        # Moris advances on 60 Hz frames while Fast keeps continuous shot times.
        self.assertAlmostEqual(fast_time, first_moris.t, delta=(1.0 / 60.0) + 1e-9)
        rel_error = abs(fast_damage - first_moris.damage) / first_moris.damage
        self.assertLessEqual(
            rel_error,
            0.01,
            f"first Snowstorm: Fast={fast_damage:,.2f}, Moris={first_moris.damage:,.2f}, rel={rel_error:.4%}",
        )


if __name__ == "__main__":
    unittest.main()
