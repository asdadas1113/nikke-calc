from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


effects_path = Path("fast_engine/engine/effects.py")
effects = effects_path.read_text(encoding="utf-8")
if "def deactivate_group(" not in effects:
    anchor = '''    def group_active(
        self,
        effect_id: int,
        targets: Iterable[int],
        *,
        now: float,
    ) -> bool:
        """Return whether this exact Moris target cohort is already active."""

        cohort = self._cohort(targets)
        if not cohort:
            return False
        return any(
            (active := self._active.get((int(effect_id), target, cohort))) is not None
            and active.active(now)
            for target in cohort
        )
'''
    addition = anchor + '''

    def deactivate_group(
        self,
        effect_id: int,
        targets: Iterable[int],
        *,
        now: float,
    ) -> tuple[int, ...]:
        """Remove one exact activation cohort without synthesizing expiry events."""

        cohort = self._cohort(targets)
        if not cohort:
            return ()
        removed: list[int] = []
        for target in cohort:
            key: ActiveKey = (int(effect_id), target, cohort)
            active = self._active.pop(key, None)
            if active is None:
                continue
            self._bullet_remaining.pop(key, None)
            effect = self._effects[active.effect_id]
            self._index_remove(effect, key)
            self.state.touch(target, StateDomain.EFFECT)
            removed.append(target)
        return tuple(removed)
'''
    effects = replace_once(effects, anchor, addition, "effects.group_active")
    effects_path.write_text(effects, encoding="utf-8")


dispatcher_path = Path("fast_engine/engine/dispatcher.py")
dispatcher = dispatcher_path.read_text(encoding="utf-8")
if "_self_stack_passive_ids" not in dispatcher:
    dispatcher = replace_once(
        dispatcher,
        '"_activation_counts", "_state_dependency_names", "_gauge_maxima",\n',
        '"_activation_counts", "_state_dependency_names", "_self_stack_passive_ids",\n'
        '        "_self_stack_dependency_names", "_gauge_maxima",\n',
        "dispatcher.slots",
    )

    init_anchor = '''        self._state_dependency_names = frozenset(
            rule.key
            for effect in self._effect_table
            if self.is_runtime_executable_effect(effect)
            for rule in effect.condition_rules
            if rule.mode in state_modes and rule.key
        )

    def enable_strict_score_delivery(self) -> None:
'''
    init_replacement = '''        self._state_dependency_names = frozenset(
            rule.key
            for effect in self._effect_table
            if self.is_runtime_executable_effect(effect)
            for rule in effect.condition_rules
            if rule.mode in state_modes and rule.key
        )
        self._self_stack_passive_ids = tuple(
            effect.effect_id
            for effect in self._effect_table
            if self._self_stack_conditional_passive_shape_supported(effect)
            and self.is_runtime_executable_effect(effect)
        )
        self._self_stack_dependency_names = frozenset(
            rule.key
            for effect_id in self._self_stack_passive_ids
            for rule in self._effect_table[effect_id].condition_rules
            if rule.key
        )

    def enable_strict_score_delivery(self) -> None:
'''
    dispatcher = replace_once(dispatcher, init_anchor, init_replacement, "dispatcher.init")

    method_anchor = '''    def can_activate_effect(self, effect: "CompiledEffect") -> bool:
'''
    methods = '''    @staticmethod
    def _self_stack_conditional_passive_shape_supported(effect: "CompiledEffect") -> bool:
        """Certify sparse Moris-style permanent passives gated by self stacks.

        Moris registers these passives at battle start even while their condition
        is false, then gates their contribution as the referenced named stack
        changes. Fast materializes only the true intervals instead: stack-provider
        transitions are sparse weapon boundaries, so no frame polling is needed.
        """
        return (
            effect.effect_type == "buff"
            and effect.duration in (None, -1.0)
            and effect.max_stack in (None, 1, 1.0)
            and target_scope_is_static(effect.target_spec)
            and effect.target_spec.runtime_supported
            and len(effect.triggers) == 1
            and effect.triggers[0].mode is TriggerMode.EVENT
            and effect.triggers[0].raw == "passive"
            and bool(effect.condition_rules)
            and all(
                rule.mode is ConditionMode.SELF_STACK_AT_LEAST and bool(rule.key)
                for rule in effect.condition_rules
            )
        )

    def _sync_self_stack_conditional_passives(self, *, now: float) -> None:
        """Materialize/de-materialize certified conditional passives on stack edges."""
        for effect_id in self._self_stack_passive_ids:
            effect = self._effect_table[effect_id]
            named_target = (
                effect.target_spec.count
                if effect.target_spec.mode.value == "named_actor"
                else None
            )
            should_be_active = self.conditions.evaluate_all(
                effect.condition_rules,
                effect_id=effect.effect_id,
                owner_actor=effect.actor,
                target_actor=named_target,
                now=now,
                context=SignalContext(),
            )
            targets = self.targets.resolve(
                effect.target_spec,
                owner_actor=effect.actor,
                now=now,
            )
            is_active = self.effects.group_active(effect.effect_id, targets, now=now)
            if should_be_active and not is_active:
                # Moris False->True here is a condition-gating transition, not
                # a fresh trigger count or generic named-buff event broadcast.
                self.effects.activate_group(effect, targets, now, self.scheduler)
            elif not should_be_active and is_active:
                self.effects.deactivate_group(effect.effect_id, targets, now=now)

'''
    dispatcher = replace_once(dispatcher, method_anchor, methods + method_anchor, "dispatcher.methods")

    consume_old = '''        if event_key == _INTERNAL_BULLET_CONSUME_EVENT:
            self.effects.consume_dynamic_bullet(owner, now=signal.time, count=1)
            return DispatchResult(())
'''
    consume_new = '''        if event_key == _INTERNAL_BULLET_CONSUME_EVENT:
            removed = self.effects.consume_dynamic_bullet(owner, now=signal.time, count=1)
            if any(
                self._effect_table[effect_id].name in self._self_stack_dependency_names
                for effect_id in removed
            ):
                self._sync_self_stack_conditional_passives(now=signal.time)
            return DispatchResult(())
'''
    dispatcher = replace_once(dispatcher, consume_old, consume_new, "dispatcher.bullet_consume")

    buff_old = '''            activated_group = self.effects.activate_group(effect, targets, now, self.scheduler)
            max_stack = effect.max_stack if effect.max_stack is not None else 1.0
'''
    buff_new = '''            activated_group = self.effects.activate_group(effect, targets, now, self.scheduler)
            if (
                activated_group
                and effect.name
                and effect.name in self._self_stack_dependency_names
            ):
                self._sync_self_stack_conditional_passives(now=now)
            max_stack = effect.max_stack if effect.max_stack is not None else 1.0
'''
    dispatcher = replace_once(dispatcher, buff_old, buff_new, "dispatcher.buff_activate")

    expiry_old = '''        expired = self.effects.handle_expiry(event)
        if expired is None:
            return

        # Moris removes all timed states first, then emits named state_end events.
'''
    expiry_new = '''        expired = self.effects.handle_expiry(event)
        if expired is None:
            return
        if expired.name and expired.name in self._self_stack_dependency_names:
            self._sync_self_stack_conditional_passives(now=event.time)

        # Moris removes all timed states first, then emits named state_end events.
'''
    dispatcher = replace_once(dispatcher, expiry_old, expiry_new, "dispatcher.expiry")
    dispatcher_path.write_text(dispatcher, encoding="utf-8")


test_path = Path("fast_engine/tests/test_conditional_passive_self_stack.py")
if not test_path.exists():
    test_path.write_text('''from __future__ import annotations

import unittest

from calculator.timeline import DEFAULT_ENEMY
from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_runtime import SimpleDamageScoreSink
from fast_engine.engine.model import EnemyStaticProfile


class ConditionalPassiveSelfStackTest(unittest.TestCase):
    def test_quency_route_completion_materializes_passive_damage_states(self) -> None:
        members = [
            "라피 : 레드 후드",
            "레드 후드",
            "프리카",
            "민트",
            "퀀시 : 이스케이프 퀸",
        ]
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        qi = members.index("퀀시 : 이스케이프 퀸")
        config = {"duration": 30.0, "first_burst_time": 3.0, "rng_mode": "expected"}
        enemy = EnemyStaticProfile(
            defense=float(DEFAULT_ENEMY.get("def", 31784.0)),
            element=DEFAULT_ENEMY.get("code"),
            core_uptime=0.0,
            core_px=0.0,
            duration=30.0,
        )
        policy = compile_burst_policy(squad, compiled, config)
        sink = SimpleDamageScoreSink(compiled, enemy)
        runtime = BurstRuntime(compiled, policy, enemy, damage_sink=sink)
        runtime.run(duration=30.0)

        effects = runtime.dispatcher.effects
        now = 29.999
        self.assertAlmostEqual(effects.sum_stat(qi, "split_dmg_pct", now=now), 49.58, places=6)
        self.assertAlmostEqual(effects.sum_stat(qi, "core_dmg_pct", now=now), 25.25, places=6)
        self.assertTrue(effects.has_named_state(qi, "루트 확정 3", now=now))
        self.assertGreaterEqual(effects.sum_stat(qi, "crit_rate", now=now), 16.73)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")
