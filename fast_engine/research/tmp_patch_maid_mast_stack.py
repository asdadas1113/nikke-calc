from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- effects.py: Moris generic harmful stack decrement with floor 1 ---
p = ROOT / 'fast_engine/engine/effects.py'
s = p.read_text(encoding='utf-8')
anchor = '''    def remove_named_state(\n        self,\n        target: int,\n        name: str,\n        *,\n        now: float,\n    ) -> tuple[int, ...]:\n'''
insert = '''    def decrement_harmful_stackable(\n        self,\n        targets: Iterable[int],\n        amount: float,\n        *,\n        now: float,\n    ) -> tuple[int, ...]:\n        \"\"\"Mirror Moris' generic debuff_stack_remove over active ally states.\n\n        The generic path only touches harmful buffs whose declared max_stack is\n        greater than one, and unlike a named removal it cannot reduce a live\n        stack below one. Runtime certification in TriggerDispatcher keeps this\n        primitive inside a squad-proven single-provider slice.\n        \"\"\"\n\n        selected = frozenset(int(target) for target in targets)\n        delta = max(0.0, float(amount))\n        if not selected or delta <= 0.0:\n            return ()\n        changed: list[int] = []\n        touched: set[int] = set()\n        for active in tuple(self._active.values()):\n            if active.target not in selected or not active.active(now):\n                continue\n            effect = self._effects[active.effect_id]\n            max_stack = effect.max_stack\n            if (\n                not str(effect.polarity or \"\").startswith(\"harmful\")\n                or max_stack is None\n                or float(max_stack) <= 1.0\n                or active.stacks <= 1.0 + _EPS\n            ):\n                continue\n            stacks = max(1.0, active.stacks - delta)\n            if abs(stacks - active.stacks) <= _EPS:\n                continue\n            active.stacks = stacks\n            touched.add(active.target)\n            if effect.name:\n                self._touch_live_reference_consumers(\n                    active.source_actor, effect.name, now=now\n                )\n            changed.append(active.effect_id)\n        for target in touched:\n            self.state.touch(target, StateDomain.EFFECT)\n        return tuple(changed)\n\n\n'''
if insert not in s:
    assert anchor in s
    s = s.replace(anchor, insert + anchor, 1)
p.write_text(s, encoding='utf-8')

# --- dispatcher.py: exact Anchor/Maid-Mast-style single-provider ownership ---
p = ROOT / 'fast_engine/engine/dispatcher.py'
s = p.read_text(encoding='utf-8')
anchor = '''    @staticmethod\n    def is_executable_effect(effect: \"CompiledEffect\") -> bool:\n'''
insert = '''    @staticmethod\n    def _generic_allies_harmful_stack_decrement_provider(\n        squad: \"CompiledSquad\", effect: \"CompiledEffect\"\n    ) -> \"CompiledEffect | None\":\n        \"\"\"Return the sole state provider for the first generic decrement slice.\n\n        Moris' target-less ``debuff_stack_remove`` walks every active harmful\n        multi-stack buff in the selected ally cohort. Fast owns that generic\n        operation only when compile-time scope proves there is exactly one such\n        possible provider, and that provider is the permanent self accuracy\n        stack used by Maid Mast. This prevents a generic cleanse from silently\n        mutating unrelated state families.\n        \"\"\"\n\n        if (\n            effect.effect_type != \"instant\"\n            or (effect.stat or \"\") != \"debuff_stack_remove\"\n            or effect.target_spec.mode is not TargetMode.ALL_ALLIES\n            or not effect.target_spec.runtime_supported\n            or effect.value is None\n            or abs(float(effect.value) - 1.0) > 1e-9\n            or effect.parameters\n            or effect.condition_rules\n            or len(effect.triggers) != 1\n        ):\n            return None\n        rule = effect.triggers[0]\n        if (\n            rule.mode is not TriggerMode.AT_LEAST\n            or rule.event_key != \"full_burst_start\"\n            or int(rule.threshold or 0) != 3\n        ):\n            return None\n\n        selected = set(possible_ally_targets(squad, effect))\n        if selected != set(range(len(squad.members))):\n            return None\n        providers = []\n        for provider in squad.effects:\n            max_stack = provider.max_stack\n            if (\n                provider.effect_type != \"buff\"\n                or not str(provider.polarity or \"\").startswith(\"harmful\")\n                or max_stack is None\n                or float(max_stack) <= 1.0\n            ):\n                continue\n            provider_targets = set(possible_ally_targets(squad, provider))\n            if selected & provider_targets:\n                providers.append(provider)\n        if len(providers) != 1:\n            return None\n        provider = providers[0]\n        if (\n            not provider.name\n            or provider.effect_type != \"buff\"\n            or (provider.stat or \"\") != \"accuracy_pct\"\n            or provider.value is None\n            or float(provider.value) >= 0.0\n            or provider.target_spec.mode is not TargetMode.SELF\n            or tuple(possible_ally_targets(squad, provider)) != (provider.actor,)\n            or provider.duration not in (None, -1.0)\n            or float(provider.max_stack or 0.0) != 3.0\n            or provider.max_trigger is not None\n            or provider.tick_interval is not None\n            or provider.parameters\n            or provider.condition_rules\n            or len(provider.triggers) != 1\n            or provider.triggers[0].mode is not TriggerMode.EVENT\n            or provider.triggers[0].event_key != \"burst_enter:1\"\n            or not is_direct_damage_buff_runtime_supported(provider)\n        ):\n            return None\n        if sum(1 for candidate in squad.effects if candidate.name == provider.name) != 1:\n            return None\n        return provider\n\n    @classmethod\n    def _generic_allies_harmful_stack_decrement_supported(\n        cls, squad: \"CompiledSquad\", effect: \"CompiledEffect\"\n    ) -> bool:\n        return cls._generic_allies_harmful_stack_decrement_provider(squad, effect) is not None\n\n'''
if insert not in s:
    assert anchor in s
    s = s.replace(anchor, insert + anchor, 1)
anchor = '''        if self._self_stack_remove_runtime_supported(effect):\n            return True\n'''
repl = '''        if self._generic_allies_harmful_stack_decrement_supported(self.squad, effect):\n            return True\n        if self._self_stack_remove_runtime_supported(effect):\n            return True\n'''
if repl not in s:
    assert anchor in s
    s = s.replace(anchor, repl, 1)
anchor = '''            elif stat == \"remove_named_buff\" and self._self_stack_remove_runtime_supported(effect):\n'''
insert = '''            elif (\n                stat == \"debuff_stack_remove\"\n                and self._generic_allies_harmful_stack_decrement_supported(\n                    self.squad, effect\n                )\n            ):\n                if any(target == ENEMY for target in targets):\n                    return False\n                changed = self.effects.decrement_harmful_stackable(\n                    tuple(int(target) for target in targets),\n                    value,\n                    now=now,\n                )\n                changed_names = {\n                    self._effect_table[effect_id].name\n                    for effect_id in changed\n                    if self._effect_table[effect_id].name\n                }\n                if changed_names & self._self_stack_dependency_names:\n                    self._sync_self_stack_conditional_passives(now=now)\n                if changed_names & self._self_state_dependency_names:\n                    self._sync_self_state_conditional_passives(now=now)\n'''
if insert not in s:
    assert anchor in s
    s = s.replace(anchor, insert + anchor, 1)
p.write_text(s, encoding='utf-8')

# --- score.py: fail closed unknown generic decrements and prove Anchor path unreachable ---
p = ROOT / 'fast_engine/engine/score.py'
s = p.read_text(encoding='utf-8')
anchor = '''def _unsupported_remove_named_buff_changes_scored_state(\n'''
insert = '''def _full_burst_end_stack_condition_unreachable_after_owned_decrement(\n    squad: CompiledSquad, effect\n) -> bool:\n    \"\"\"Prove a max-stack full-burst-end condition false after owned decrement.\n\n    The owned provider gains exactly one stack at each B1 entry (max three). The\n    sole generic mutator begins on full-burst start #3 and removes one stack. With\n    no burst re-entry or competing named-state mutator, full-burst end therefore\n    sees 1, 2, then 2 forever; a ``self_stack_at_least:...:3`` consumer cannot fire.\n    \"\"\"\n\n    if (\n        len(effect.triggers) != 1\n        or effect.triggers[0].mode is not TriggerMode.EVENT\n        or effect.triggers[0].event_key != \"full_burst_end\"\n        or len(effect.condition_rules) != 1\n    ):\n        return False\n    condition = effect.condition_rules[0]\n    if condition.mode is not ConditionMode.SELF_STACK_AT_LEAST or not condition.key:\n        return False\n    providers = tuple(\n        provider\n        for provider in squad.effects\n        if provider.name == condition.key\n        and provider.actor == effect.actor\n    )\n    if len(providers) != 1:\n        return False\n    provider = providers[0]\n    if float(provider.max_stack or 0.0) != 3.0 or float(condition.value or 0.0) != 3.0:\n        return False\n    mutators = tuple(\n        candidate\n        for candidate in squad.effects\n        if TriggerDispatcher._generic_allies_harmful_stack_decrement_provider(\n            squad, candidate\n        ) is provider\n    )\n    if len(mutators) != 1:\n        return False\n    if any(\n        (other.stat or \"\").startswith(\"burst_stage_override:reenter\")\n        for other in squad.effects\n    ):\n        return False\n    for other in squad.effects:\n        if other.effect_id in {provider.effect_id, effect.effect_id, mutators[0].effect_id}:\n            continue\n        if other.name == provider.name:\n            return False\n        target_name = other.parameters.get(\"target_effect\")\n        if target_name == provider.name and (other.stat or \"\") in {\n            \"remove_named_buff\", \"buff_stack_add\", \"buff_stack_remove\",\n            \"debuff_stack_add\", \"debuff_stack_remove\",\n        }:\n            return False\n        if (other.stat or \"\") in {\"buff_stack_remove\", \"debuff_stack_remove\"} and not target_name:\n            if other.effect_id != mutators[0].effect_id:\n                return False\n    return True\n\n\ndef _unsupported_generic_harmful_stack_remove_changes_scored_state(\n    squad: CompiledSquad, effect\n) -> bool:\n    \"\"\"Fail closed when an unowned generic decrement can mutate scored state.\"\"\"\n\n    if (\n        effect.effect_type != \"instant\"\n        or (effect.stat or \"\") != \"debuff_stack_remove\"\n        or effect.parameters.get(\"target_effect\")\n        or _is_patternless_unreachable(effect)\n    ):\n        return False\n    if TriggerDispatcher._generic_allies_harmful_stack_decrement_supported(\n        squad, effect\n    ):\n        return False\n    mutator_targets = set(_possible_ally_targets(squad, effect))\n    if not mutator_targets:\n        return False\n    for provider in squad.effects:\n        max_stack = provider.max_stack\n        if (\n            provider.effect_type != \"buff\"\n            or not str(provider.polarity or \"\").startswith(\"harmful\")\n            or max_stack is None\n            or float(max_stack) <= 1.0\n            or (provider.stat or \"\") not in DIRECT_DAMAGE_STATE_STATS\n        ):\n            continue\n        if not _direct_damage_buff_score_supported(squad, provider):\n            continue\n        if mutator_targets & set(_possible_ally_targets(squad, provider)):\n            return True\n    return False\n\n\n'''
if insert not in s:
    assert anchor in s
    s = s.replace(anchor, insert + anchor, 1)
anchor = '''    if _roster_static_burst1_condition_unreachable(squad, effect):\n        return False\n'''
repl = '''    if _roster_static_burst1_condition_unreachable(squad, effect):\n        return False\n    if _full_burst_end_stack_condition_unreachable_after_owned_decrement(\n        squad, effect\n    ):\n        return False\n'''
if repl not in s:
    assert anchor in s
    s = s.replace(anchor, repl, 1)
anchor = '''    for effect in squad.effects:\n        if _dynamic_rank_target_transaction_unsafe(squad, effect):\n'''
insert = '''    for effect in squad.effects:\n        if _unsupported_generic_harmful_stack_remove_changes_scored_state(\n            squad, effect\n        ):\n            owner = squad.members[effect.actor].name\n            blockers.append(\n                f\"normal_state:{owner}:{effect.name or 'debuff_stack_remove'}:debuff_stack_remove\"\n            )\n\n'''
if insert not in s:
    assert anchor in s
    s = s.replace(anchor, insert + anchor, 1)
p.write_text(s, encoding='utf-8')

# --- focused regression ---
p = ROOT / 'fast_engine/tests/test_damage_maid_mast_stack_mutation.py'
p.write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import (
    _full_burst_end_stack_condition_unreachable_after_owned_decrement,
    static_score_blockers,
)


class MaidMastStackMutationTests(unittest.TestCase):
    ANCHOR_PUBLIC = ('스쿼드4', '레이드_앨리스브래디', '레이드_볼륨')
    NO_ANCHOR_PUBLIC = ('레이드_루주', '레이드_브리드디젤')

    @staticmethod
    def _compiled(label):
        members = list(snapshot.SQUADS[label]['members'])
        moris = spec.build_squad(members)
        return moris, compile_moris_squad(moris)

    @staticmethod
    def _effect(compiled, owner, name):
        actor = compiled.names.index(owner)
        return next(e for e in compiled.members[actor].effects if e.name == name)

    @staticmethod
    def _append_effect(compiled, actor, effect):
        member = compiled.members[actor]
        member = replace(member, effects=member.effects + (effect,))
        return replace(
            compiled,
            members=tuple(member if i == actor else row for i, row in enumerate(compiled.members)),
        )

    def test_anchor_public_scope_has_one_owned_harmful_stack_provider(self):
        for label in self.ANCHOR_PUBLIC:
            with self.subTest(label=label):
                _moris, compiled = self._compiled(label)
                mutator = self._effect(compiled, '앵커 : 이노센트 메이드', '불가사리(모양) 오므라이스 3')
                provider = TriggerDispatcher._generic_allies_harmful_stack_decrement_provider(
                    compiled, mutator
                )
                self.assertIsNotNone(provider)
                self.assertEqual(provider.name, '취기')
                self.assertEqual(compiled.members[provider.actor].name, '마스트 : 로망틱 메이드')

    def test_fast_matches_moris_third_full_burst_anchor_decrement(self):
        moris, compiled = self._compiled('스쿼드4')
        policy = compile_burst_policy(moris, compiled, {'duration': 29.0, 'first_burst_time': 3.0})
        runtime = BurstRuntime(
            compiled,
            policy,
            EnemyStaticProfile(duration=29.0, core_px=0.0),
        )
        runtime.run(duration=29.0)
        mast = compiled.names.index('마스트 : 로망틱 메이드')
        self.assertEqual(runtime.dispatcher.effects.named_stack(mast, '취기', now=29.0), 2.0)

        result = simulate(
            moris,
            config={'duration': 29.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
            seed=42,
            verbose=True,
        )
        drunk = [e for e in result.log.buff_events if e.name == '취기']
        self.assertTrue(drunk)
        self.assertEqual(drunk[-1].stack, 2)
        starts = [float(e.t) for e in result.log.burst_log if e.event == 'full_burst 시작']
        self.assertAlmostEqual(float(drunk[-1].t), starts[2], places=9)

    def test_anchor_makes_full_burst_end_stack3_consumers_unreachable(self):
        for label in self.ANCHOR_PUBLIC:
            with self.subTest(label=label):
                _moris, compiled = self._compiled(label)
                remover = self._effect(compiled, '마스트 : 로망틱 메이드', '파이레츠 스피릿 3')
                hangover = self._effect(compiled, '마스트 : 로망틱 메이드', '숙취')
                self.assertTrue(
                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(
                        compiled, remover
                    )
                )
                self.assertTrue(
                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(
                        compiled, hangover
                    )
                )
                blockers = set(static_score_blockers(compiled))
                self.assertNotIn(
                    'normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff',
                    blockers,
                )

    def test_no_anchor_reachable_remover_stays_fail_closed(self):
        for label in self.NO_ANCHOR_PUBLIC:
            with self.subTest(label=label):
                _moris, compiled = self._compiled(label)
                remover = self._effect(compiled, '마스트 : 로망틱 메이드', '파이레츠 스피릿 3')
                self.assertFalse(
                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(
                        compiled, remover
                    )
                )
                self.assertIn(
                    'normal_state:마스트 : 로망틱 메이드:파이레츠 스피릿 3:remove_named_buff',
                    set(static_score_blockers(compiled)),
                )

    def test_extra_harmful_multistack_state_rejects_generic_ownership(self):
        _moris, compiled = self._compiled('스쿼드4')
        mutator = self._effect(compiled, '앵커 : 이노센트 메이드', '불가사리(모양) 오므라이스 3')
        drunk = self._effect(compiled, '마스트 : 로망틱 메이드', '취기')
        extra = replace(
            drunk,
            effect_id=max(e.effect_id for e in compiled.effects) + 1,
            actor=0,
            name='extra harmful stack',
        )
        guarded = self._append_effect(compiled, 0, extra)
        self.assertIsNone(
            TriggerDispatcher._generic_allies_harmful_stack_decrement_provider(
                guarded, mutator
            )
        )
        self.assertIn(
            'normal_state:앵커 : 이노센트 메이드:불가사리(모양) 오므라이스 3:debuff_stack_remove',
            set(static_score_blockers(guarded)),
        )

    def test_burst_reentry_invalidates_unreachable_proof(self):
        _moris, compiled = self._compiled('스쿼드4')
        remover = self._effect(compiled, '마스트 : 로망틱 메이드', '파이레츠 스피릿 3')
        source = compiled.members[0].effects[0]
        extra = replace(
            source,
            effect_id=max(e.effect_id for e in compiled.effects) + 1,
            stat='burst_stage_override:reenter1',
            name='synthetic reenter',
        )
        guarded = self._append_effect(compiled, 0, extra)
        self.assertFalse(
            _full_burst_end_stack_condition_unreachable_after_owned_decrement(
                guarded, remover
            )
        )


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')

print('patched Maid Mast / Anchor generic stack decrement slice')
