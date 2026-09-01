from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage import DamageTerms
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.normal_attack import NormalAttackSpec, expected_normal_shot_damage
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.score import static_normal_score_blockers
from fast_engine.engine.state import StateStore


class WeaponModeToggleDamageTests(unittest.TestCase):
    @staticmethod
    def _spec() -> NormalAttackSpec:
        return NormalAttackSpec(
            coeff_per_hit=100.0,
            hits_per_shot=1,
            core_dmg_mult=200.0,
            full_charge_mult=100.0,
            normal_hit_coeff=1.0,
            is_full_charge=False,
        )

    def test_pierce_enabled_turns_on_pierce_damage_layer(self):
        base = expected_normal_shot_damage(
            self._spec(),
            base_atk=1000.0,
            enemy_def=500.0,
            terms=DamageTerms(crit_rate=0.0, pierce_dmg_pct=50.0),
            core_prob=0.0,
        )
        pierced = expected_normal_shot_damage(
            self._spec(),
            base_atk=1000.0,
            enemy_def=500.0,
            terms=DamageTerms(
                crit_rate=0.0,
                pierce_dmg_pct=50.0,
                pierce_enabled=True,
            ),
            core_prob=0.0,
        )
        self.assertAlmostEqual(base, 500.0)
        self.assertAlmostEqual(pierced, 750.0)

    def test_armor_break_enabled_zeroes_defense_and_uses_type_bonus(self):
        base = expected_normal_shot_damage(
            self._spec(),
            base_atk=1000.0,
            enemy_def=500.0,
            terms=DamageTerms(crit_rate=0.0, armor_break_dmg_pct=20.0),
            core_prob=0.0,
        )
        broken = expected_normal_shot_damage(
            self._spec(),
            base_atk=1000.0,
            enemy_def=500.0,
            terms=DamageTerms(
                crit_rate=0.0,
                armor_break_dmg_pct=20.0,
                armor_break_enabled=True,
            ),
            core_prob=0.0,
        )
        self.assertAlmostEqual(base, 500.0)
        self.assertAlmostEqual(broken, 1200.0)

    def test_real_supported_toggle_effects_leave_normal_state_blocker_lane(self):
        names = ["목단", "타키나", "치사토", "스노우 화이트 : 헤비암즈", "에이다"]
        compiled = compile_moris_squad(build_squad(names))
        wanted = {
            ("타키나", "제압 개시 2", "armor_break_enabled"),
            ("치사토", "방어 관통 사격", "armor_break_enabled"),
            ("스노우 화이트 : 헤비암즈", "어나더 화이트 관통특화", "pierce_enabled"),
        }
        found = set()
        for effect in compiled.effects:
            key = (
                compiled.names[effect.actor],
                effect.name,
                effect.stat or "",
            )
            if key in wanted:
                found.add(key)
                self.assertTrue(
                    is_direct_damage_buff_runtime_supported(effect),
                    key,
                )
        self.assertEqual(found, wanted)

        blockers = static_normal_score_blockers(compiled)
        for owner, name, stat in wanted:
            label = f"{owner}:{name}:{stat}"
            self.assertNotIn(f"normal_state:{label}", blockers)
            self.assertNotIn(f"normal_delivery:{label}", blockers)

    def test_active_toggle_is_resolved_by_presence_not_numeric_value(self):
        compiled = compile_moris_squad(
            build_squad(["타키나"]),
            require_five=False,
        )
        effect = next(
            effect
            for effect in compiled.effects
            if effect.name == "제압 개시 2"
            and effect.stat == "armor_break_enabled"
        )
        self.assertIsNone(effect.value)

        state = StateStore.from_compiled_squad(compiled)
        effects = ActiveEffectStore(compiled, state)
        effects.activate(effect, effect.actor, 0.0, EventScheduler())
        resolver = DamageTermResolver(
            compiled,
            effects,
            state,
            EnemyStaticProfile(duration=10.0),
        )
        self.assertTrue(resolver.resolve(effect.actor, now=0.0).armor_break_enabled)

    def test_hp_conditioned_pierce_remains_fail_closed(self):
        compiled = compile_moris_squad(
            build_squad(["앨리스"]),
            require_five=False,
        )
        effect = next(
            effect
            for effect in compiled.effects
            if effect.name == "건강한 당근"
            and effect.stat == "pierce_enabled"
        )
        self.assertFalse(is_direct_damage_buff_runtime_supported(effect))
        self.assertIn(
            "normal_delivery:앨리스:건강한 당근:pierce_enabled",
            static_normal_score_blockers(compiled),
        )


if __name__ == "__main__":
    unittest.main()
