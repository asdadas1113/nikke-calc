from __future__ import annotations

from pathlib import Path


RUNTIME = Path("fast_engine/engine/damage_runtime.py")
TEST = Path("fast_engine/tests/test_damage_state_end_named_stack.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_runtime() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .damage_state import DamageTermResolver\n",
        "from .damage_state import DamageTermResolver\nfrom .dispatcher import TriggerDispatcher\n",
        "dispatcher import",
    )

    anchor = '''    def _weapon_hit_chain_shape_supported(self, source: "CompiledEffect") -> bool:\n'''
    helpers = '''    @staticmethod
    def _finite_self_state_end_provider_shape_supported(
        provider: "CompiledEffect",
    ) -> bool:
        """Prove the narrow producer whose finite expiry emits a state_end event."""
        return (
            provider.effect_type == "buff"
            and provider.target_spec.mode is TargetMode.SELF
            and provider.duration is not None
            and float(provider.duration) > 0.0
            and provider.max_stack in (None, 1, 1.0)
            and provider.tick_interval is None
            and provider.parameters.get("duration_bullets") is None
            and not provider.parameters
            and bool(provider.triggers)
            and all(rule.is_runtime_supported for rule in provider.condition_rules)
            and TriggerDispatcher.is_executable_effect(provider)
        )

    def _finite_self_state_end_source_supported(
        self,
        effect: "CompiledEffect",
    ) -> bool:
        if not effect.triggers:
            return False
        for rule in effect.triggers:
            key = rule.event_key or ""
            if rule.mode is not TriggerMode.EVENT or not key.startswith("event:state_end:"):
                return False
            name = key[len("event:state_end:"):]
            if not name:
                return False
            providers = [
                provider
                for provider in self.squad.effects
                if provider.effect_id != effect.effect_id
                and provider.actor == effect.actor
                and provider.name == name
                and self._finite_self_state_end_provider_shape_supported(provider)
            ]
            if len(providers) != 1:
                return False
        return True

    @staticmethod
    def _regular_enemy_named_stack_shape_supported(
        provider: "CompiledEffect",
    ) -> bool:
        """Finite harmful enemy stack whose live count is directly observable."""
        return (
            provider.effect_type == "buff"
            and (provider.stat or "") == "received_dmg_pct"
            and (provider.polarity or "").startswith("harmful")
            and bool(provider.name)
            and provider.target_spec.mode is TargetMode.ENEMY
            and provider.value is not None
            and provider.max_stack is not None
            and float(provider.max_stack) > 1.0
            and provider.duration is not None
            and float(provider.duration) > 0.0
            and provider.tick_interval is None
            and provider.parameters.get("duration_bullets") is None
            and not provider.parameters
            and bool(provider.triggers)
            and all(rule.is_runtime_supported for rule in provider.condition_rules)
            and TriggerDispatcher.is_executable_effect(provider)
        )

    def _regular_enemy_named_stack_provider(
        self,
        actor: int,
        name: str,
    ) -> "CompiledEffect | None":
        providers = [
            provider
            for provider in self.squad.effects
            if provider.actor == actor
            and provider.name == name
            and self._regular_enemy_named_stack_shape_supported(provider)
        ]
        return providers[0] if len(providers) == 1 else None

    def _state_end_enemy_stack_damage_shape_supported(
        self,
        effect: "CompiledEffect",
    ) -> bool:
        ref = effect.parameters.get("scaling_ref")
        return (
            effect.effect_type == "damage"
            and (effect.stat or "") == "bonus_damage"
            and effect.target_spec.mode is TargetMode.ENEMY
            and effect.parameters.get("scaling") == "stack_count"
            and isinstance(ref, str)
            and bool(ref)
            and set(effect.parameters) == {"scaling", "scaling_ref"}
            and not effect.condition_rules
            and self._finite_self_state_end_source_supported(effect)
            and self._regular_enemy_named_stack_provider(effect.actor, ref) is not None
        )

    def _state_end_enemy_stack_remove_shape_supported(
        self,
        effect: "CompiledEffect",
    ) -> bool:
        ref = effect.parameters.get("target_effect")
        return (
            effect.effect_type == "instant"
            and (effect.stat or "") == "remove_named_buff"
            and effect.target_spec.mode is TargetMode.ENEMY
            and isinstance(ref, str)
            and bool(ref)
            and set(effect.parameters) == {"target_effect"}
            and not effect.condition_rules
            and self._finite_self_state_end_source_supported(effect)
            and self._regular_enemy_named_stack_provider(effect.actor, ref) is not None
        )

'''
    text = replace_once(text, anchor, helpers + anchor, "state-end helpers")

    old_shape = '''        providers = [
            other for other in self.squad.effects
            if other.actor == effect.actor
            and other.name == spec.ref
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        return len(providers) == 1

    def _gauge_ref_runtime_supported'''
    new_shape = '''        providers = [
            other for other in self.squad.effects
            if other.actor == effect.actor
            and other.name == spec.ref
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        if len(providers) == 1:
            return True
        return self._state_end_enemy_stack_damage_shape_supported(effect)

    def _gauge_ref_runtime_supported'''
    text = replace_once(text, old_shape, new_shape, "stack shape")

    old_runtime = '''        providers = [
            other for other in self.squad.effects
            if other.actor == effect.actor
            and other.name == spec.ref
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        if len(providers) != 1:
            return False
        if self.runtime is None:
            return True
        return self.runtime.dispatcher.can_activate_effect(providers[0])

    @staticmethod
    def _state_effect_patternless_unreachable'''
    new_runtime = '''        providers = [
            other for other in self.squad.effects
            if other.actor == effect.actor
            and other.name == spec.ref
            and self._enemy_named_stack_marker_shape_supported(other)
        ]
        provider = providers[0] if len(providers) == 1 else None
        if provider is None and self._state_end_enemy_stack_damage_shape_supported(effect):
            provider = self._regular_enemy_named_stack_provider(effect.actor, spec.ref)
        if provider is None:
            return False
        if self.runtime is None:
            return True
        return self.runtime.dispatcher.can_activate_effect(provider)

    @staticmethod
    def _state_effect_patternless_unreachable'''
    text = replace_once(text, old_runtime, new_runtime, "stack runtime")

    old_state_support = '''    def supports_state_operation(self, effect: "CompiledEffect") -> bool:
        if not self._state_operation_shape_supported(effect):
            return False
        name = str(effect.parameters.get("target_effect") or "")
        ids = self._stateful_dot_names.get(name, ())
        if not ids:
            return False
        if self.runtime is None:
            return True
        return any(
            self._stateful_dot_runtime_supported(self.squad.effects[effect_id])
            for effect_id in ids
        )
'''
    new_state_support = '''    def supports_state_operation(self, effect: "CompiledEffect") -> bool:
        if self._state_end_enemy_stack_remove_shape_supported(effect):
            name = str(effect.parameters.get("target_effect") or "")
            provider = self._regular_enemy_named_stack_provider(effect.actor, name)
            if provider is None:
                return False
            if self.runtime is None:
                return True
            return self.runtime.dispatcher.can_activate_effect(provider)
        if not self._state_operation_shape_supported(effect):
            return False
        name = str(effect.parameters.get("target_effect") or "")
        ids = self._stateful_dot_names.get(name, ())
        if not ids:
            return False
        if self.runtime is None:
            return True
        return any(
            self._stateful_dot_runtime_supported(self.squad.effects[effect_id])
            for effect_id in ids
        )
'''
    text = replace_once(text, old_state_support, new_state_support, "state operation support")

    old_delivery = '''    def _delivery_supported(self, effect: "CompiledEffect") -> bool:
        if effect.target_spec.mode is not TargetMode.ENEMY:
            return False
        if not all(rule.is_runtime_supported for rule in effect.condition_rules):
            return False
        if not effect.triggers:
            return False
        for rule in effect.triggers:
            if rule.mode is TriggerMode.PERIODIC:
                if rule.interval is None or float(rule.interval) <= 0.0:
                    return False
                continue
            if rule.event_key not in _SAFE_EVENT_KEYS:
                if not (
                    (rule.event_key or "").startswith("weapon_hit:")
                    and self._weapon_hit_consumer_source_proven(effect, rule.event_key or "")
                ):
                    return False
            if rule.event_key == "core_hit" and not is_static_expected_core_count_rule(rule):
                return False
        return True
'''
    new_delivery = '''    def _delivery_supported(self, effect: "CompiledEffect") -> bool:
        if effect.target_spec.mode is not TargetMode.ENEMY:
            return False
        if not all(rule.is_runtime_supported for rule in effect.condition_rules):
            return False
        if not effect.triggers:
            return False
        state_end_stack = self._state_end_enemy_stack_damage_shape_supported(effect)
        for rule in effect.triggers:
            if rule.mode is TriggerMode.PERIODIC:
                if rule.interval is None or float(rule.interval) <= 0.0:
                    return False
                continue
            if rule.event_key not in _SAFE_EVENT_KEYS:
                key = rule.event_key or ""
                if state_end_stack and key.startswith("event:state_end:"):
                    continue
                if not (
                    key.startswith("weapon_hit:")
                    and self._weapon_hit_consumer_source_proven(effect, key)
                ):
                    return False
            if rule.event_key == "core_hit" and not is_static_expected_core_count_rule(rule):
                return False
        return True
'''
    text = replace_once(text, old_delivery, new_delivery, "delivery")

    RUNTIME.write_text(text, encoding="utf-8")


def write_test() -> None:
    TEST.write_text('''from __future__ import annotations

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

    def test_real_asuka_damage_and_remove_open_without_little_mermaid_leak(self):
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
        self.assertTrue(
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
''', encoding="utf-8")


def main() -> None:
    patch_runtime()
    write_test()
    print("installed finite self-state-end + enemy named-stack damage slice")


if __name__ == "__main__":
    main()
