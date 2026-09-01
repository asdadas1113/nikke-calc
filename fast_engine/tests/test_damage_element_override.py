from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_static_element_override_score_supported
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_normal_score_blockers
from fast_engine.engine.state import StateStore


NAMES = [
    "라피 : 레드 후드",
    "리틀 머메이드",
    "크라운",
    "마스트 : 로망틱 메이드",
    "헬름",
]


class ElementOverrideDamageTests(unittest.TestCase):
    @staticmethod
    def _compiled():
        return compile_moris_squad(build_squad(NAMES))

    @staticmethod
    def _rapi_override(squad):
        return next(
            effect
            for effect in squad.members[0].effects
            if effect.name == "부착형 유탄"
            and effect.stat == "element_code_override"
        )

    def test_real_rapi_static_override_matches_moris_element_or_semantics(self):
        squad = self._compiled()
        effect = self._rapi_override(squad)

        self.assertTrue(is_static_element_override_score_supported(effect))
        self.assertNotIn(
            "normal_state:라피 : 레드 후드:부착형 유탄:element_code_override",
            static_normal_score_blockers(squad),
        )

        state = StateStore.from_compiled_squad(squad)
        effects = ActiveEffectStore(squad, state)

        def element_match(enemy_code: str | None) -> bool:
            resolver = DamageTermResolver(
                squad,
                effects,
                state,
                EnemyStaticProfile(element=enemy_code),
            )
            return resolver.resolve(0, now=0.0).element_match

        # Rapi: Red Hood's roster code is Fire. Her permanent override grants
        # advantage against Electric without changing that roster code.
        self.assertTrue(element_match("전격"))
        # Native Fire -> Wind advantage remains intact.
        self.assertTrue(element_match("풍압"))
        self.assertFalse(element_match("수냉"))
        self.assertFalse(element_match(None))

    def test_mutable_override_shape_remains_fail_closed(self):
        squad = self._compiled()
        effect = self._rapi_override(squad)
        mutable = replace(effect, duration=10.0)
        self.assertFalse(is_static_element_override_score_supported(mutable))

        first = replace(squad.members[0], effects=(mutable,))
        unsafe = replace(squad, members=(first,) + squad.members[1:])
        self.assertIn(
            "normal_state:라피 : 레드 후드:부착형 유탄:element_code_override",
            static_normal_score_blockers(unsafe),
        )


if __name__ == "__main__":
    unittest.main()
