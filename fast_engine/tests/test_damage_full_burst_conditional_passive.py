from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.timeline import DT, simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import compile_condition
from fast_engine.engine.damage_policy import (
    full_burst_conditional_permanent_passive_shape,
    is_direct_damage_buff_runtime_supported,
)
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.targets import TargetMode


class FullBurstConditionalPassiveTests(unittest.TestCase):
    MEMBERS = [
        '라피 : 레드 후드', '레드 후드', '프리카', '민트', '도로시 : 세렌디피티'
    ]

    def _fixture(self):
        squad = spec.build_squad(self.MEMBERS)
        compiled = compile_moris_squad(squad)
        actor = self.MEMBERS.index('도로시 : 세렌디피티')
        effect = next(e for e in compiled.members[actor].effects if e.name == '광익 2')
        accuracy = next(e for e in compiled.members[actor].effects if e.name == '광익 3')
        return squad, compiled, actor, effect, accuracy

    def test_real_dorothy_shape_is_owned_but_accuracy_neighbor_is_not(self):
        _squad, compiled, _actor, effect, accuracy = self._fixture()
        self.assertTrue(full_burst_conditional_permanent_passive_shape(effect))
        self.assertTrue(is_direct_damage_buff_runtime_supported(effect))
        self.assertFalse(full_burst_conditional_permanent_passive_shape(accuracy))
        self.assertFalse(is_direct_damage_buff_runtime_supported(accuracy))

        public = compile_moris_squad(
            spec.build_squad(list(snapshot.SQUADS['스쿼드3']['members']))
        )
        blockers = set(static_score_blockers(public))
        self.assertNotIn(
            'normal_delivery:도로시 : 세렌디피티:광익 2:atk_pct', blockers
        )
        self.assertNotIn(
            'skill_state_delivery:도로시 : 세렌디피티:광익 2:atk_pct', blockers
        )
        self.assertIn(
            'normal_delivery:도로시 : 세렌디피티:광익 3:accuracy_pct', blockers
        )

    def test_fast_materializes_exactly_on_full_burst_phase_edges(self):
        squad, compiled, _actor, effect, _accuracy = self._fixture()
        events = []
        original_activate = ActiveEffectStore.activate_group
        original_deactivate = ActiveEffectStore.deactivate_group

        def activate(store, candidate, targets, now, scheduler):
            out = original_activate(store, candidate, targets, now, scheduler)
            if candidate.effect_id == effect.effect_id and out:
                events.append(('activate', float(now)))
            return out

        def deactivate(store, effect_id, targets, now):
            out = original_deactivate(store, effect_id, targets, now=now)
            if effect_id == effect.effect_id and out:
                events.append(('expire', float(now)))
            return out

        policy = compile_burst_policy(
            squad, compiled, {'duration': 30.0, 'first_burst_time': 3.0}
        )
        with patch.object(ActiveEffectStore, 'activate_group', new=activate), patch.object(
            ActiveEffectStore, 'deactivate_group', new=deactivate
        ):
            result = BurstRuntime(compiled, policy).run(duration=30.0)

        expected = []
        for i, start in enumerate(result.full_burst_starts):
            expected.append(('activate', float(start)))
            if i < len(result.full_burst_ends):
                expected.append(('expire', float(result.full_burst_ends[i])))
        self.assertEqual(events, expected)
        self.assertEqual(len(result.full_burst_starts), 3)
        self.assertEqual(len(result.full_burst_ends), 2)

    def test_moris_transition_log_is_one_tick_after_live_phase_edge(self):
        squad, compiled, _actor, _effect, _accuracy = self._fixture()
        policy = compile_burst_policy(
            squad, compiled, {'duration': 30.0, 'first_burst_time': 3.0}
        )
        fast = BurstRuntime(compiled, policy).run(duration=30.0)
        moris = simulate(
            squad,
            config={'duration': 30.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
            verbose=True,
        )
        rows = [row for row in moris.log.buff_events if row.name == '광익 2']
        expected_edges = []
        for i, start in enumerate(fast.full_burst_starts):
            expected_edges.append(('activate', float(start)))
            if i < len(fast.full_burst_ends):
                expected_edges.append(('expire', float(fast.full_burst_ends[i])))
        self.assertEqual([row.kind for row in rows], [kind for kind, _ in expected_edges])
        self.assertEqual(len(rows), 5)
        for row, (_kind, edge) in zip(rows, expected_edges):
            self.assertAlmostEqual(float(row.t) - edge, DT, places=9)

    def test_neighboring_shapes_remain_fail_closed(self):
        _squad, _compiled, _actor, effect, _accuracy = self._fixture()
        self.assertFalse(full_burst_conditional_permanent_passive_shape(replace(effect, max_stack=2)))
        self.assertFalse(full_burst_conditional_permanent_passive_shape(replace(effect, target_spec=replace(effect.target_spec, mode=TargetMode.ALL_ALLIES))))
        self.assertFalse(full_burst_conditional_permanent_passive_shape(replace(effect, parameters={'x': 1})))
        self.assertFalse(full_burst_conditional_permanent_passive_shape(replace(
            effect,
            conditions=('not_during_full_burst',),
            condition_rules=(compile_condition('not_during_full_burst'),),
        )))


if __name__ == '__main__':
    unittest.main()