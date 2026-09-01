from __future__ import annotations

import unittest

from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile


class _TrackingDamageSink(SimpleDamageScoreSink):
    __slots__ = ("effect_total",)

    def __init__(self, squad, enemy) -> None:
        super().__init__(squad, enemy)
        self.effect_total: dict[int, float] = {}

    def _score_spec(self, effect_id: int, *, now: float, full_burst: bool) -> bool:
        actor = self._effect_actor.get(effect_id)
        before = None if actor is None else self.char_total[actor]
        fired = super()._score_spec(
            effect_id,
            now=now,
            full_burst=full_burst,
        )
        if fired and actor is not None and before is not None:
            self.effect_total[effect_id] = (
                self.effect_total.get(effect_id, 0.0)
                + self.char_total[actor]
                - before
            )
        return fired


class ManaFixedDotParityTests(unittest.TestCase):
    NAMES = ["미카", "아니스", "마나"]
    DOT_NAME = "페이탈 에러! 2"
    DURATION = 11.0

    def test_one_burst_fixed_dot_matches_moris(self):
        squad = build_squad(self.NAMES)
        compiled = compile_moris_squad(squad, require_five=False)
        config = {
            "duration": self.DURATION,
            "rng_mode": "expected",
            "first_burst_time": 0.0,
            "max_burst_count": 1,
            "burst_sequence": [
                {"1": ["미카"], "2": ["아니스"], "3": ["마나"]}
            ],
        }
        policy = compile_burst_policy(squad, compiled, config)
        enemy = EnemyStaticProfile(duration=self.DURATION)
        sink = _TrackingDamageSink(compiled, enemy)

        actor = self.NAMES.index("마나")
        effect = next(
            effect for effect in compiled.members[actor].effects
            if effect.name == self.DOT_NAME
        )
        self.assertEqual(effect.stat, "dot_damage")
        self.assertIn(effect.effect_id, sink.dot_specs)

        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        runtime.run(duration=self.DURATION)

        moris = simulate(squad, config=config, verbose=True)
        authority_hits = [
            hit for hit in moris.hits
            if hit.caster == "마나" and hit.skill_name == self.DOT_NAME
        ]
        authority = sum(hit.damage for hit in authority_hits)
        estimate = sink.effect_total.get(effect.effect_id, 0.0)

        # Delayed 1s ticks over a 10s duration: exactly ten ticks.
        self.assertEqual(len(authority_hits), 10)
        self.assertGreater(authority, 0.0)
        self.assertGreater(estimate, 0.0)
        rel_error = abs(estimate - authority) / authority
        self.assertLessEqual(
            rel_error,
            0.01,
            f"Mana fixed DoT: Fast={estimate:,.2f}, Moris={authority:,.2f}, rel={rel_error:.4%}",
        )


if __name__ == "__main__":
    unittest.main()
