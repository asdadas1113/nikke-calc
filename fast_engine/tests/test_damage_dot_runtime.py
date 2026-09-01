from __future__ import annotations

import unittest
from dataclasses import replace

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage import DamageTerms
from fast_engine.engine.damage_events import expected_damage_event
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.triggers import TriggerIndex, TriggerMode, TriggerRule


class FixedDotRuntimeTests(unittest.TestCase):
    @staticmethod
    def _fixture(*, immediate: bool, horizon: float = 3.5):
        compiled = compile_moris_squad(build_squad(["마나"]), require_five=False)
        source = next(
            effect for effect in compiled.members[0].effects
            if effect.name == "페이탈 에러! 2"
        )
        params = dict(source.parameters)
        if immediate:
            params["tick_start"] = "immediate"
        else:
            params.pop("tick_start", None)
        effect = replace(
            source,
            effect_id=0,
            actor_effect_index=0,
            triggers=(TriggerRule("battle_start", "battle_start", TriggerMode.EVENT),),
            duration=3.0,
            tick_interval=1.0,
            max_stack=1.0,
            parameters=params,
        )
        member = replace(compiled.members[0], effects=(effect,))
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects((effect,), actor_count=1),
        )
        enemy = EnemyStaticProfile(duration=horizon)
        sink = SimpleDamageScoreSink(squad, enemy)
        policy = BurstPolicy(
            duration=horizon,
            first_burst_time=99.0,
            no_burst_actors=frozenset({0}),
        )
        return squad, enemy, sink, policy, effect

    @staticmethod
    def _one_tick(squad, enemy, sink, effect) -> float:
        spec = sink.dot_specs[effect.effect_id]
        return expected_damage_event(
            spec.damage,
            squad.members[0],
            enemy,
            DamageTerms(),
            full_burst=False,
        )

    def test_delayed_dot_ticks_at_interval_and_includes_expiry_boundary(self):
        squad, enemy, sink, policy, effect = self._fixture(immediate=False)
        self.assertIn(effect.effect_id, sink.dot_specs)
        one = self._one_tick(squad, enemy, sink, effect)
        runtime = BurstRuntime(squad, policy, enemy, damage_sink=sink)
        runtime.run(duration=3.5)
        # Moris type-2 DoT: t=1,2,3 for duration=3 and interval=1.
        self.assertAlmostEqual(sink.char_total[0], one * 3, places=7)

    def test_immediate_dot_starts_now_and_excludes_expiry_boundary(self):
        squad, enemy, sink, policy, effect = self._fixture(immediate=True)
        one = self._one_tick(squad, enemy, sink, effect)
        runtime = BurstRuntime(squad, policy, enemy, damage_sink=sink)
        runtime.run(duration=3.5)
        # Moris type-1 DoT: t=0,1,2; the t=3 expiry tick is excluded.
        self.assertAlmostEqual(sink.char_total[0], one * 3, places=7)

    def test_combat_horizon_remains_half_open_even_for_expiry_tick(self):
        squad, enemy, sink, policy, effect = self._fixture(
            immediate=False,
            horizon=3.0,
        )
        one = self._one_tick(squad, enemy, sink, effect)
        runtime = BurstRuntime(squad, policy, enemy, damage_sink=sink)
        runtime.run(duration=3.0)
        # DoT itself would tick at t=3, but combat is [0, 3), matching Moris.
        self.assertAlmostEqual(sink.char_total[0], one * 2, places=7)


if __name__ == "__main__":
    unittest.main()
