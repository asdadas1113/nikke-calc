from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_state import DamageTermResolver
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.state import StateStore


class DamageStateCacheTests(unittest.TestCase):
    def setUp(self):
        self.squad = compile_moris_squad(
            build_squad(["리타", "크라운", "홍련", "앨리스", "나가"])
        )
        self.state = StateStore.from_compiled_squad(self.squad)
        self.effects = ActiveEffectStore(self.squad, self.state)
        self.scheduler = EventScheduler()
        self.enemy = EnemyStaticProfile(element="수냉")
        self.resolver = DamageTermResolver(
            self.squad, self.effects, self.state, self.enemy
        )
        self.atk_effect = next(
            effect
            for effect in self.squad.effects
            if effect.effect_type == "buff"
            and effect.stat == "atk_pct"
            and float(effect.value or 0.0) != 0.0
        )

    def test_repeated_resolve_reuses_same_snapshot_object(self):
        first = self.resolver.resolve(0, now=0.0)
        second = self.resolver.resolve(0, now=1.0)
        self.assertIs(first, second)

    def test_resource_change_does_not_invalidate_damage_terms(self):
        first = self.resolver.resolve(0, now=0.0)
        self.state.set_ammo(0, max(self.state.actors[0].ammo - 1.0, 0.0))
        second = self.resolver.resolve(0, now=0.1)
        self.assertIs(first, second)

    def test_unrelated_actor_effect_change_does_not_invalidate_actor_zero(self):
        first = self.resolver.resolve(0, now=0.0)
        self.effects.activate_group(
            self.atk_effect, (1,), 0.0, self.scheduler
        )
        second = self.resolver.resolve(0, now=0.1)
        self.assertIs(first, second)

    def test_target_actor_effect_change_invalidates_and_recomputes(self):
        first = self.resolver.resolve(0, now=0.0)
        self.effects.activate_group(
            self.atk_effect, (0,), 0.0, self.scheduler
        )
        second = self.resolver.resolve(0, now=0.1)
        self.assertIsNot(first, second)
        self.assertGreater(second.atk_pct, first.atk_pct)


if __name__ == "__main__":
    unittest.main()
