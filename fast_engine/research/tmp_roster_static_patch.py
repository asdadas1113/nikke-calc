from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


p = Path('fast_engine/engine/score.py')
s = p.read_text(encoding='utf-8')
anchor = '''def _unsupported_remove_named_buff_changes_scored_state(\n    squad: CompiledSquad,\n    effect,\n    damage_sink,\n) -> bool:\n'''
helper = '''def _roster_static_burst1_condition_unreachable(\n    squad: CompiledSquad, effect\n) -> bool:\n    \"\"\"Prove a has/no-B1 condition false from the immutable roster.\n\n    Fast evaluates these conditions through ``BurstMachine.stage_for()``, so the\n    compiled burst stage is static only while no *other* actor can mutate its\n    stage. Re-enter overrides are owner-local and do not alter an ally's stage,\n    but any ``burst_stage_override:*`` effect on another actor makes this proof\n    fail closed.\n    \"\"\"\n\n    if len(effect.condition_rules) != 1:\n        return False\n    rule = effect.condition_rules[0]\n    if rule.mode not in {\n        ConditionMode.HAS_BURST1_ALLY,\n        ConditionMode.NO_BURST1_ALLY,\n    }:\n        return False\n    if any(\n        other.actor != effect.actor\n        and (other.stat or \"\").startswith(\"burst_stage_override:\")\n        for other in squad.effects\n    ):\n        return False\n\n    has_burst1_ally = any(\n        actor != effect.actor and member.burst_stage == \"1\"\n        for actor, member in enumerate(squad.members)\n    )\n    return (\n        not has_burst1_ally\n        if rule.mode is ConditionMode.HAS_BURST1_ALLY\n        else has_burst1_ally\n    )\n\n\n'''
s = replace_once(s, anchor, helper + anchor, 'score helper')
old = '''    if _is_patternless_unreachable(effect):\n        return False\n    if TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(\n'''
new = '''    if _is_patternless_unreachable(effect):\n        return False\n    if _roster_static_burst1_condition_unreachable(squad, effect):\n        return False\n    if TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(\n'''
s = replace_once(s, old, new, 'remove guard')
p.write_text(s, encoding='utf-8')

Path('fast_engine/tests/test_damage_roster_static_named_remove.py').write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.score import (
    _roster_static_burst1_condition_unreachable,
    static_score_blockers,
)


class RosterStaticNamedRemoveTests(unittest.TestCase):
    PUBLIC_ANIS = ('스쿼드5', '레이드_앨리스브래디', '레이드_일레그')

    @staticmethod
    def _compiled(label: str):
        members = list(snapshot.SQUADS[label]['members'])
        squad = spec.build_squad(members)
        return members, squad, compile_moris_squad(squad)

    @staticmethod
    def _anis_effect(compiled, name: str):
        actor = compiled.names.index('아니스 : 스타')
        return next(e for e in compiled.members[actor].effects if e.name == name)

    @staticmethod
    def _replace_actor_effect(compiled, actor: int, original_id: int, replacement):
        member = compiled.members[actor]
        member = replace(
            member,
            effects=tuple(
                replacement if e.effect_id == original_id else e
                for e in member.effects
            ),
        )
        return replace(
            compiled,
            members=tuple(member if i == actor else row for i, row in enumerate(compiled.members)),
        )

    def test_public_anis_star_remover_is_provably_unreachable_and_blocker_disappears(self):
        for label in self.PUBLIC_ANIS:
            with self.subTest(label=label):
                _members, _squad, compiled = self._compiled(label)
                remover = self._anis_effect(compiled, '스타 폴 4')
                self.assertTrue(_roster_static_burst1_condition_unreachable(compiled, remover))
                blockers = set(static_score_blockers(compiled))
                self.assertNotIn(
                    'normal_state:아니스 : 스타:스타 폴 4:remove_named_buff',
                    blockers,
                )
                self.assertIn('cadence:아니스 : 스타:슈팅 스타2:charge_time_fixed', blockers)
                self.assertIn('skill_damage:아니스 : 스타:슈팅 스타1:auto_damage', blockers)
                self.assertIn(
                    'skill_state_delivery:아니스 : 스타:스타더스트 3:projectile_explosion_dmg_pct',
                    blockers,
                )

    def test_complementary_no_b1_remover_is_reachable_in_public_roster(self):
        _members, _squad, compiled = self._compiled('스쿼드5')
        remover = self._anis_effect(compiled, '스타 폴 2')
        self.assertFalse(_roster_static_burst1_condition_unreachable(compiled, remover))

    def test_b1_control_reverses_the_two_static_branches(self):
        members = ['아니스 : 스타', '리틀 머메이드', '이사벨', '신데렐라', '크라운']
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        star_fall_4 = self._anis_effect(compiled, '스타 폴 4')
        star_fall_2 = self._anis_effect(compiled, '스타 폴 2')
        self.assertFalse(_roster_static_burst1_condition_unreachable(compiled, star_fall_4))
        self.assertTrue(_roster_static_burst1_condition_unreachable(compiled, star_fall_2))

    def test_any_ally_stage_override_makes_static_proof_fail_closed(self):
        _members, _squad, compiled = self._compiled('스쿼드5')
        remover = self._anis_effect(compiled, '스타 폴 4')
        anis = compiled.names.index('아니스 : 스타')
        ally = next(i for i in range(5) if i != anis)
        source = compiled.members[ally].effects[0]
        mutated = replace(source, stat='burst_stage_override:1')
        guarded = self._replace_actor_effect(compiled, ally, source.effect_id, mutated)
        self.assertFalse(_roster_static_burst1_condition_unreachable(guarded, remover))

    def test_public_moris_keeps_my_star_and_b1_control_uses_everyones_star(self):
        _members, squad, _compiled = self._compiled('레이드_앨리스브래디')
        result = simulate(
            squad,
            config={'duration': 30.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
            seed=42,
            verbose=True,
        )
        my_star = [e for e in result.log.buff_events if e.name == '나만의 별']
        every_star = [e for e in result.log.buff_events if e.name == '모두의 별']
        ends = [float(e.t) for e in result.log.burst_log if e.event == 'full_burst 종료']
        self.assertTrue(my_star)
        self.assertFalse(every_star)
        self.assertEqual([float(e.t) for e in my_star], [0.0] + ends)
        self.assertFalse(any(e.kind == 'expire' for e in my_star))

        control = spec.build_squad(
            ['아니스 : 스타', '리틀 머메이드', '이사벨', '신데렐라', '크라운']
        )
        control_result = simulate(
            control,
            config={'duration': 30.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
            seed=42,
            verbose=True,
        )
        self.assertFalse(any(e.name == '나만의 별' for e in control_result.log.buff_events))
        self.assertTrue(any(e.name == '모두의 별' for e in control_result.log.buff_events))


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')
