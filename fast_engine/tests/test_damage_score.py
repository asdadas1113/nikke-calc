from __future__ import annotations

import unittest

from calculator.sim_result import _is_normal
from calculator.timeline import simulate
from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_normal_squad, static_normal_score_blockers


class StaticNormalScoreParityTests(unittest.TestCase):
    NAMES = ["라피", "폴리", "프로덕트 12", "델타", "아니스"]
    DURATION = 30.0

    @classmethod
    def setUpClass(cls):
        cls.moris_squad = build_squad(cls.NAMES)
        cls.compiled = compile_moris_squad(cls.moris_squad)
        cls.config = {
            "duration": cls.DURATION,
            "rng_mode": "expected",
        }
        cls.policy = compile_burst_policy(cls.moris_squad, cls.compiled, cls.config)
        cls.blockers = static_normal_score_blockers(cls.compiled)

    def test_reference_fixture_is_safe_for_static_normal_scoring(self):
        details = []
        for effect in self.compiled.effects:
            if effect.name != "포메이션 F.F":
                continue
            details.append(
                "effect="
                + repr(
                    {
                        "actor": self.compiled.members[effect.actor].name,
                        "stat": effect.stat,
                        "timings": [rule.raw for rule in effect.triggers],
                        "conditions": list(effect.conditions),
                        "target": effect.target,
                        "duration": effect.duration,
                        "value": effect.value,
                    }
                )
            )
        message = "\n".join((*self.blockers, *details))
        self.assertEqual(self.blockers, (), message)

    def test_fast_normal_damage_stays_close_to_moris_expected_normal_damage(self):
        if self.blockers:
            self.skipTest("fixture is intentionally fail-closed; see blocker test")

        enemy = EnemyStaticProfile(duration=self.DURATION)
        fast = score_static_normal_squad(
            self.compiled,
            self.policy,
            enemy,
            duration=self.DURATION,
        )
        moris = simulate(
            self.moris_squad,
            config=self.config,
            verbose=True,
        )

        moris_by_name = {
            name: sum(
                hit.damage
                for hit in moris.hits
                if hit.caster == name and _is_normal(hit)
            )
            for name in self.NAMES
        }
        moris_total = sum(moris_by_name.values())

        self.assertGreater(moris_total, 0)
        self.assertIn("skill_damage:not_implemented", fast.unsupported)

        for actor, name in enumerate(self.NAMES):
            authority = float(moris_by_name[name])
            estimate = float(fast.char_total[actor])
            if authority <= 0.0:
                self.assertEqual(estimate, 0.0, name)
                continue
            rel_error = abs(estimate - authority) / authority
            self.assertLessEqual(
                rel_error,
                0.01,
                f"{name}: Fast={estimate:,.2f}, Moris={authority:,.2f}, rel={rel_error:.4%}",
            )

        team_rel_error = abs(fast.squad_total - moris_total) / moris_total
        self.assertLessEqual(
            team_rel_error,
            0.01,
            f"team: Fast={fast.squad_total:,.2f}, Moris={moris_total:,.2f}, rel={team_rel_error:.4%}",
        )


if __name__ == "__main__":
    unittest.main()
