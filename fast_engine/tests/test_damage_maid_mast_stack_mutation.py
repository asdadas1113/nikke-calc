from __future__ import annotations

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
                self.assertTrue(
                    _full_burst_end_stack_condition_unreachable_after_owned_decrement(
                        compiled, remover
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
