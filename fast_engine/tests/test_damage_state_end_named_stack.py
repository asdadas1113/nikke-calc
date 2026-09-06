from __future__ import annotations

from dataclasses import replace
import unittest

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import SignalContext
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.state import ENEMY
from fast_engine.engine.triggers import compile_trigger_rule


NAMES = [
    "리틀 머메이드",
    "델타 : 닌자 시프",
    "크라운",
    "아스카 : WILLE",
    "라피 : 레드 후드",
]
ASUKA = 3


class StateEndNamedStackDamageTests(unittest.TestCase):
    @staticmethod
    def _fixture():
        squad = compile_moris_squad(build_squad(NAMES))
        by_name = {
            effect.name: effect
            for effect in squad.effects
            if effect.actor == ASUKA
        }
        sink = SimpleDamageScoreSink(
            squad,
            EnemyStaticProfile(defense=0.0, duration=25.0),
        )
        return squad, sink, by_name

    def test_real_asuka_damage_and_remove_coexist_with_owned_little_mermaid_lifecycle(self):
        squad, sink, by_name = self._fixture()
        annihilation = by_name["섬멸"]
        remove = by_name["섬멸 2"]

        self.assertTrue(sink.supports(annihilation))
        self.assertTrue(sink.supports_state_operation(remove))
        blockers = static_score_blockers(squad)
        self.assertNotIn(
            "skill_damage:아스카 : WILLE:섬멸:bonus_damage",
            blockers,
        )
        # Little Mermaid is now opened only by its own separately proven
        # replacement + squad-ammo lifecycle; Asuka state-end ownership must not
        # be the reason it becomes executable. At the integrated public fixture
        # both independent proofs are present, so neither blocker remains.
        self.assertFalse(
            any("리틀 머메이드:거품 난사" in blocker for blocker in blockers),
            blockers,
        )

    def test_runtime_reads_live_enemy_stack_then_named_remove_clears_it(self):
        squad, sink, by_name = self._fixture()
        provider = by_name["안티 AT 필드"]
        annihilation = by_name["섬멸"]
        remove = by_name["섬멸 2"]
        enemy = EnemyStaticProfile(defense=0.0, duration=5.0)
        runtime = BurstRuntime(
            squad,
            BurstPolicy(
                duration=5.0,
                no_burst_actors=frozenset(range(len(squad.members))),
            ),
            enemy,
            damage_sink=sink,
        )

        for _ in range(3):
            runtime.dispatcher.effects.activate_group(
                provider,
                (ENEMY,),
                1.0,
                runtime.scheduler,
            )
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "안티 AT 필드", now=2.0),
            3.0,
        )
        self.assertEqual(sink._stack_count_hit_count(annihilation.effect_id), 3)

        before = sink.char_total[ASUKA]
        self.assertTrue(
            sink.activate(
                annihilation,
                now=2.0,
                targets=(ENEMY,),
                context=SignalContext(),
            )
        )
        self.assertGreater(sink.char_total[ASUKA], before)
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "안티 AT 필드", now=2.0),
            3.0,
        )
        self.assertTrue(
            sink.activate_state_operation(remove, now=2.0, targets=(ENEMY,))
        )
        self.assertEqual(
            runtime.dispatcher.effects.named_stack(ENEMY, "안티 AT 필드", now=2.0),
            0.0,
        )

    def test_provider_shapes_fail_closed(self):
        _squad, sink, by_name = self._fixture()
        state = by_name["섬멸 태세"]
        stack = by_name["안티 AT 필드"]

        self.assertTrue(sink._finite_self_state_end_provider_shape_supported(state))
        self.assertFalse(
            sink._finite_self_state_end_provider_shape_supported(
                replace(state, duration=-1.0)
            )
        )
        self.assertFalse(
            sink._finite_self_state_end_provider_shape_supported(
                replace(state, target=stack.target, target_spec=stack.target_spec)
            )
        )

        self.assertTrue(sink._regular_enemy_named_stack_shape_supported(stack))
        self.assertFalse(
            sink._regular_enemy_named_stack_shape_supported(
                replace(stack, max_stack=1.0)
            )
        )
        self.assertFalse(
            sink._regular_enemy_named_stack_shape_supported(
                replace(stack, parameters={"mutable": True})
            )
        )
        self.assertIsNone(
            sink._regular_enemy_named_stack_provider(ASUKA - 1, "안티 AT 필드")
        )

    def test_arbitrary_named_events_targets_and_removals_stay_closed(self):
        _squad, sink, by_name = self._fixture()
        annihilation = by_name["섬멸"]
        remove = by_name["섬멸 2"]
        state = by_name["섬멸 태세"]

        arbitrary = replace(
            annihilation,
            triggers=(compile_trigger_rule("event:not_proven"),),
        )
        unknown_state = replace(
            annihilation,
            triggers=(compile_trigger_rule("event:state_end:not_proven"),),
        )
        self_target = replace(
            annihilation,
            target=state.target,
            target_spec=state.target_spec,
        )
        wrong_remove = replace(
            remove,
            parameters={"target_effect": "not_proven"},
        )

        self.assertFalse(sink._delivery_supported(arbitrary))
        self.assertFalse(sink._delivery_supported(unknown_state))
        self.assertFalse(sink._delivery_supported(self_target))
        self.assertFalse(sink.supports_state_operation(wrong_remove))


if __name__ == "__main__":
    unittest.main()
