from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.last_bullet import simulate_static_last_bullet_boundaries
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers


NAMES = [
    "미란다",
    "브리드 : 사일런트 트랙",
    "헬름",
    "루주",
    "미하라 : 본딩 체인",
]
CONFIG = {
    "duration": 180.0,
    "first_burst_time": 3.0,
    "rng_mode": "expected",
}
EXPECTED_MIHARA_GAPS = (
    "skill_damage:미하라 : 본딩 체인:바디 컨텍 3:damage",
    "skill_damage:미하라 : 본딩 체인:사슬 감기:dot_damage",
    "skill_damage:미하라 : 본딩 체인:사슬 당기기:dot_damage",
)


class RealSquadCertificationTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        moris_squad = build_squad(NAMES)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, CONFIG)
        enemy = EnemyStaticProfile(
            defense=31784.0,
            element=None,
            core_uptime=0.0,
            core_px=0.0,
            duration=180.0,
        )
        return moris_squad, compiled, policy, enemy

    def test_control_miranda_mihara_reaches_only_explicit_mihara_damage_gap(self):
        _moris_squad, compiled, policy, enemy = self._fixture()

        # Helm last_bullet and Rouge back_row delivery are now certified. Any
        # remaining gap must stay explicit in FastScore.unsupported rather than
        # being mistaken for a complete ranking score.
        self.assertEqual(static_score_blockers(compiled), ())

        score = score_static_squad(compiled, policy, enemy)
        self.assertGreater(score.squad_total, 0.0)
        self.assertGreater(score.events_processed, 0)
        self.assertEqual(score.unsupported, EXPECTED_MIHARA_GAPS)

    def test_real_helm_last_bullet_still_activates_on_dynamic_charge_path(self):
        moris_squad, compiled, _policy, enemy = self._fixture()
        helm = next(
            effect
            for effect in compiled.effects
            if effect.actor == 2
            and effect.name == "진두지휘"
            and effect.stat == "normal_atk_crit_rate"
        )
        rows = simulate_static_last_bullet_boundaries(
            compiled,
            duration=30.0,
            effect_filter=lambda effect: effect.effect_id == helm.effect_id,
        )
        self.assertTrue(rows)
        first = rows[0].time
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {**CONFIG, "duration": first + 0.01},
        )
        runtime = BurstRuntime(compiled, policy, enemy)
        runtime.run(duration=first + 0.01)

        # This squad routes Helm through MultiSignalChargeCadenceRuntime because
        # a squad-body-hit consumer exists. The post-shot last_bullet signal must
        # still activate Helm's all-allies crit-rate state there.
        self.assertTrue(runtime.weapons.emits_every_charge_shot(2))
        helm_value = runtime.dispatcher.effects.sum_stat(
            2, "normal_atk_crit_rate", now=first + 0.001
        )
        ally_value = runtime.dispatcher.effects.sum_stat(
            0, "normal_atk_crit_rate", now=first + 0.001
        )
        self.assertGreater(helm_value, 0.0)
        self.assertAlmostEqual(ally_value, helm_value, places=9)


if __name__ == "__main__":
    unittest.main()
