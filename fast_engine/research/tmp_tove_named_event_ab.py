from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[:a] + replacement + text[b:]


def baseline() -> None:
    from context import snapshot, spec
    from fast_engine.engine.compiler import compile_moris_squad
    import fast_engine.engine.score as score

    squad = compile_moris_squad(spec.build_squad(list(snapshot.SQUADS["레이드_소다"]["members"])))
    consumer = next(
        e for e in squad.effects
        if squad.members[e.actor].name == "토브" and e.name == "임시 개조 2"
    )
    blockers = score.static_score_blockers(squad)
    print("baseline direct score supported", score._direct_damage_buff_score_supported(squad, consumer))
    print("baseline Tove blockers", [b for b in blockers if "토브" in b])
    assert not score._direct_damage_buff_score_supported(squad, consumer)
    assert "normal_delivery:토브:임시 개조 2:crit_dmg" in blockers
    assert "skill_state_delivery:토브:임시 개조 2:crit_dmg" in blockers


def named_provider_proof_body(indent: str) -> str:
    i = indent
    return f'''{i}providers = tuple(
{i}    provider
{i}    for provider in PROVIDERS
{i}    if provider.effect_id != effect.effect_id
{i}    and provider.name == name
{i})
{i}if not providers:
{i}    return False
{i}for provider in providers:
{i}    if provider.effect_type == "instant":
{i}        if (
{i}            provider.actor != effect.actor
{i}            or (provider.stat or "") != "ammo_charge_pct"
{i}            or provider.value is None
{i}            or float(provider.value) < 0.0
{i}            or any(rule.event_key == "battle_start" for rule in provider.triggers)
{i}            or not provider.target_spec.runtime_supported
{i}            or not POSSIBLE_TARGETS
{i}            or not TriggerDispatcher.is_executable_effect(provider)
{i}        ):
{i}            return False
{i}        continue
{i}    if provider.effect_type != "buff":
{i}        return False
{i}    if TriggerDispatcher._named_event_keys(provider):
{i}        return False
{i}    if provider.parameters.get("event_scope") not in (None, "", "squad", "recipients"):
{i}        return False
{i}    if not provider.target_spec.runtime_supported:
{i}        return False
{i}    if not (
{i}        TriggerDispatcher.is_executable_effect(provider)
{i}        or TriggerDispatcher._named_event_marker_nop_shape_supported(provider)
{i}    ):
{i}        return False
'''


def patch_runner_worktree() -> None:
    dispatcher = Path("fast_engine/engine/dispatcher.py")
    text = dispatcher.read_text()
    text = replace_between(
        text,
        '            elif stat in {"ammo_charge_pct", "ammo_charge_flat"}:\n',
        '            elif stat == "force_reload":\n',
        '''            elif stat in {"ammo_charge_pct", "ammo_charge_flat"}:
                if self._ammo_charge_sink is None or any(target == ENEMY for target in targets):
                    return False
                actor_targets = tuple(int(target) for target in targets)
                if not self._ammo_charge_sink(stat, actor_targets, value, now):
                    return False
                # Moris emits event:{name} after successful percent refill only.
                if (
                    stat == "ammo_charge_pct"
                    and effect.name
                    and effect.name in self._named_event_names_needed
                ):
                    from .burst import BurstSignal
                    self.dispatch(
                        BurstSignal(now, f"event:{effect.name}", effect.actor, effect.actor)
                    )
''',
    )

    # Runtime source certification mirrors the score proof below. This is needed
    # because can_activate_effect() calls is_runtime_executable_effect().
    start = '    def _named_event_source_runtime_safe(self, effect: "CompiledEffect") -> bool:\n'
    end = '    def is_runtime_executable_effect(self, effect: "CompiledEffect") -> bool:\n'
    replacement = '''    def _named_event_source_runtime_safe(self, effect: "CompiledEffect") -> bool:
        keys = self._named_event_keys(effect)
        if not keys:
            return True
        for key in keys:
            if key == "event:heal_received":
                if not self.heal_received_dependency_score_safe(self.squad, effect):
                    return False
                continue
            name = key[len("event:"):]
            providers = tuple(
                provider
                for provider in self._effect_table
                if provider.effect_id != effect.effect_id
                and provider.name == name
            )
            if not providers:
                return False
            for provider in providers:
                if provider.effect_type == "instant":
                    if (
                        provider.actor != effect.actor
                        or (provider.stat or "") != "ammo_charge_pct"
                        or provider.value is None
                        or float(provider.value) < 0.0
                        or any(rule.event_key == "battle_start" for rule in provider.triggers)
                        or not provider.target_spec.runtime_supported
                        or not possible_ally_targets(self.squad, provider)
                        or not self.is_executable_effect(provider)
                    ):
                        return False
                    continue
                if provider.effect_type != "buff":
                    return False
                if self._named_event_keys(provider):
                    return False
                if provider.parameters.get("event_scope") not in (None, "", "squad", "recipients"):
                    return False
                if not provider.target_spec.runtime_supported:
                    return False
                if not (
                    self.is_executable_effect(provider)
                    or self._named_event_marker_nop_shape_supported(provider)
                ):
                    return False
        return True

'''
    text = replace_between(text, start, end, replacement)
    dispatcher.write_text(text)

    score_path = Path("fast_engine/engine/score.py")
    text = score_path.read_text()
    text = replace_between(
        text,
        "def _ammo_charge_named_event_safe(squad: CompiledSquad, effect) -> bool:\n",
        "def _ammo_charge_recipient_score_safe(squad: CompiledSquad, actor: int) -> bool:\n",
        '''def _ammo_charge_named_event_safe(squad: CompiledSquad, effect) -> bool:
    if not effect.name:
        return True
    event_key = f"event:{effect.name}"
    consumers = tuple(
        other
        for other in squad.effects
        if other.effect_id != effect.effect_id
        and any(rule.event_key == event_key for rule in other.triggers)
    )
    if not consumers:
        return True
    if (effect.stat or "") != "ammo_charge_pct":
        return False
    return all(
        consumer.actor == effect.actor
        and consumer.effect_type == "buff"
        and is_direct_damage_buff_runtime_supported(consumer)
        for consumer in consumers
    )


''',
    )
    text = replace_between(
        text,
        "def _named_buff_event_dependency_score_safe(squad: CompiledSquad, effect) -> bool:\n",
        "def _direct_damage_buff_score_supported(squad: CompiledSquad, effect) -> bool:\n",
        '''def _named_buff_event_dependency_score_safe(squad: CompiledSquad, effect) -> bool:
    keys = TriggerDispatcher._named_event_keys(effect)
    if not keys:
        return True
    for key in keys:
        if key == "event:heal_received":
            if not TriggerDispatcher.heal_received_dependency_score_safe(squad, effect):
                return False
            continue
        name = key[len("event:"):]
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != effect.effect_id
            and provider.name == name
        )
        if not providers:
            return False
        for provider in providers:
            if provider.effect_type == "instant":
                if (
                    provider.actor != effect.actor
                    or (provider.stat or "") != "ammo_charge_pct"
                    or provider.value is None
                    or float(provider.value) < 0.0
                    or any(rule.event_key == "battle_start" for rule in provider.triggers)
                    or not provider.target_spec.runtime_supported
                    or not _possible_ally_targets(squad, provider)
                    or not TriggerDispatcher.is_executable_effect(provider)
                ):
                    return False
                continue
            if provider.effect_type != "buff":
                return False
            if TriggerDispatcher._named_event_keys(provider):
                return False
            if provider.parameters.get("event_scope") not in (None, "", "squad", "recipients"):
                return False
            if not provider.target_spec.runtime_supported:
                return False
            if not (
                TriggerDispatcher.is_executable_effect(provider)
                or TriggerDispatcher._named_event_marker_nop_shape_supported(provider)
            ):
                return False
    return True


''',
    )
    score_path.write_text(text)

    # Existing regression encodes the old Tove fail-closed expectation. Flip only
    # that assertion in the runner worktree; production promotion will update it.
    test_path = Path("fast_engine/tests/test_named_buff_event_runtime.py")
    text = test_path.read_text()
    old = '        self.assertTrue(any("토브:임시 개조 2:crit_dmg" in item for item in blockers))\n'
    new = '        self.assertFalse(any("토브:임시 개조 2:crit_dmg" in item for item in blockers))\n'
    if old not in text:
        raise RuntimeError("old Tove named-event expectation not found")
    test_path.write_text(text.replace(old, new, 1))


def write_tmp_regression() -> None:
    Path("fast_engine/tests/test_tmp_tove_pct_named_event.py").write_text(
        '''from __future__ import annotations

import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
import fast_engine.engine.score as score
from fast_engine.tests.test_damage_dynamic_ammo_charge import _ammo_effect, _named_consumer, _squad


class TovePctInstantNamedEventABTests(unittest.TestCase):
    def test_synthetic_pct_provider_emits_named_event_and_is_score_safe(self):
        refill = _ammo_effect(stat="ammo_charge_pct", value=25.0)
        followup = _named_consumer()
        squad = _squad((refill, followup))
        blockers = score.static_score_blockers(squad)
        self.assertNotIn("cadence:synthetic-reload:refill:ammo_charge_pct", blockers)
        self.assertNotIn("normal_delivery:synthetic-reload:named followup:atk_pct", blockers)
        runtime = BurstRuntime(squad, BurstPolicy(duration=5.0, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=5.0))
        runtime.dispatcher.attach_ammo_charge_sink(lambda stat, targets, value, now: True)
        runtime.dispatcher.dispatch(BurstSignal(1.0, "burst_cast", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(refill.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(followup.effect_id, 0), 1)
        self.assertAlmostEqual(runtime.dispatcher.effects.sum_stat(0, "atk_pct", now=1.01), 10.0, places=9)

    def test_flat_named_provider_remains_fail_closed_and_does_not_emit(self):
        refill = _ammo_effect(stat="ammo_charge_flat", value=1.0)
        followup = _named_consumer()
        squad = _squad((refill, followup))
        self.assertIn("cadence:synthetic-reload:refill:ammo_charge_flat", score.static_score_blockers(squad))
        runtime = BurstRuntime(squad, BurstPolicy(duration=5.0, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=5.0))
        runtime.dispatcher.attach_ammo_charge_sink(lambda stat, targets, value, now: True)
        runtime.dispatcher.dispatch(BurstSignal(1.0, "burst_cast", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(refill.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(followup.effect_id, 0), 0)

    def test_real_tove_consumer_source_is_certified_and_runtime_event_fires(self):
        squad = compile_moris_squad(spec.build_squad(list(snapshot.SQUADS["레이드_소다"]["members"])))
        tove = next(i for i, member in enumerate(squad.members) if member.name == "토브")
        provider = next(e for e in squad.members[tove].effects if e.name == "급조 탄환")
        followup = next(e for e in squad.members[tove].effects if e.name == "임시 개조 2")
        self.assertTrue(score._direct_damage_buff_score_supported(squad, followup))
        blockers = score.static_score_blockers(squad)
        self.assertNotIn("normal_delivery:토브:임시 개조 2:crit_dmg", blockers)
        self.assertNotIn("skill_state_delivery:토브:임시 개조 2:crit_dmg", blockers)
        self.assertIn("cadence:토브:임시 개조:max_ammo_flat", blockers)
        runtime = BurstRuntime(squad, BurstPolicy(duration=5.0, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=5.0))
        runtime.dispatcher.attach_ammo_charge_sink(lambda stat, targets, value, now: True)
        for n in range(10):
            runtime.dispatcher.dispatch(BurstSignal(0.1 * n, "hit_count", tove, tove))
        self.assertEqual(runtime.dispatcher._activation_counts.get(provider.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(followup.effect_id, 0), 1)
        for actor in range(len(squad.members)):
            self.assertAlmostEqual(runtime.dispatcher.effects.sum_stat(actor, "crit_dmg", now=0.91), float(followup.value or 0.0), places=9)


if __name__ == "__main__":
    unittest.main()
'''
    )


def public_delta() -> None:
    from context import snapshot, spec
    from fast_engine.engine.compiler import compile_moris_squad
    from fast_engine.engine.score import static_score_blockers

    for team in ("레이드_소다", "스쿼드3"):
        squad = compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]["members"])))
        blockers = static_score_blockers(squad)
        print("\n", team)
        print("\n".join(blockers))
        assert "normal_delivery:토브:임시 개조 2:crit_dmg" not in blockers
        assert "skill_state_delivery:토브:임시 개조 2:crit_dmg" not in blockers
        assert any(item.startswith("cadence:토브:") for item in blockers)


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    baseline()
    patch_runner_worktree()
    run("git", "diff", "--check")
    run("git", "diff", "--", "fast_engine/engine/dispatcher.py", "fast_engine/engine/score.py", "fast_engine/tests/test_named_buff_event_runtime.py")
    write_tmp_regression()
    run(sys.executable, "-m", "unittest", "-v", "fast_engine.tests.test_damage_dynamic_ammo_charge", "fast_engine.tests.test_named_buff_event_runtime", "fast_engine.tests.test_tmp_tove_pct_named_event")
    public_delta()
    run(sys.executable, "-m", "unittest", "discover", "-s", "fast_engine/tests", "-p", "test_*.py")


if __name__ == "__main__":
    main()
