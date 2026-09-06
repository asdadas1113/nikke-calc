from __future__ import annotations

from dataclasses import replace
from math import isclose
import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstMachine, BurstPolicy, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.control_lifecycle import certified_stack3_self_stun_remove_lifecycles
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.dynamic_rapid import DynamicRapidCadenceRuntime
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.score import _dynamic_rapid_reload_score_actors, static_score_blockers
from fast_engine.engine.state import StateStore
from fast_engine.engine.triggers import compile_trigger_rule


class MaidMastHangoverLifecycleTests(unittest.TestCase):
    PUBLIC = ('레이드_루주', '레이드_브리드디젤')
    MAST = '마스트 : 로망틱 메이드'

    @staticmethod
    def _compiled(label='레이드_루주'):
        members = list(snapshot.SQUADS[label]['members'])
        moris = spec.build_squad(members)
        return moris, compile_moris_squad(moris)

    @staticmethod
    def _effect(compiled, actor, name):
        return next(row for row in compiled.members[actor].effects if row.name == name)

    @staticmethod
    def _append(compiled, actor, effect):
        member = compiled.members[actor]
        member = replace(member, effects=member.effects + (effect,))
        return replace(
            compiled,
            members=tuple(member if i == actor else row for i, row in enumerate(compiled.members)),
        )

    def test_public_exact_lifecycle_is_the_only_owned_control_family(self):
        for label in self.PUBLIC:
            with self.subTest(label=label):
                _moris, compiled = self._compiled(label)
                owned = certified_stack3_self_stun_remove_lifecycles(compiled)
                self.assertEqual(len(owned), 1)
                row = owned[0]
                self.assertEqual(compiled.members[row.actor].name, self.MAST)
                control = compiled.effects[row.control_effect_id]
                remover = compiled.effects[row.remover_effect_id]
                self.assertEqual(control.name, '숙취')
                self.assertEqual(control.duration, 10.0)
                self.assertEqual(remover.name, '파이레츠 스피릿 3')
                self.assertIn(row.actor, _dynamic_rapid_reload_score_actors(compiled))
                self.assertNotIn(
                    f'normal_state:{self.MAST}:파이레츠 스피릿 3:remove_named_buff',
                    set(static_score_blockers(compiled)),
                )

    def test_runtime_activates_hangover_then_removes_only_drunk_state(self):
        for label in self.PUBLIC:
            with self.subTest(label=label):
                moris, compiled = self._compiled(label)
                policy = compile_burst_policy(
                    moris, compiled, {'duration': 90.0, 'first_burst_time': 3.0}
                )
                probe = BurstRuntime(
                    compiled, policy, EnemyStaticProfile(duration=90.0, core_px=0.0)
                )
                probe_result = probe.run(duration=90.0)
                row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
                start = probe_result.full_burst_ends[2]
                runtime = BurstRuntime(
                    compiled, policy, EnemyStaticProfile(duration=90.0, core_px=0.0)
                )
                runtime.run(duration=start + 1e-5)
                end = runtime.dispatcher.control_block_until(row.actor, start + 1e-6)
                self.assertIsNotNone(end)
                self.assertAlmostEqual(end, start + 10.0, places=9)
                self.assertIsNone(
                    runtime.dispatcher.effects.active_control_until(
                        row.actor, (row.control_effect_id,), now=start + 10.0
                    )
                )
                self.assertEqual(
                    runtime.dispatcher.effects.named_stack(row.actor, '취기', now=start + 1e-6),
                    0.0,
                )
                self.assertTrue(
                    runtime.dispatcher.effects.has_named_state(row.actor, '숙취', now=start + 1e-6)
                )
                for passive_id in row.passive_effect_ids:
                    passive = compiled.effects[passive_id]
                    self.assertFalse(any(
                        active.effect_id == passive.effect_id and active.active(start + 1e-6)
                        for active in runtime.dispatcher.effects._active.values()
                    ))

    def test_next_b1_restarts_drunk_and_passives_while_hangover_survives(self):
        moris, compiled = self._compiled('레이드_루주')
        policy = compile_burst_policy(moris, compiled, {'duration': 90.0, 'first_burst_time': 3.0})
        probe = BurstRuntime(compiled, policy, EnemyStaticProfile(duration=90.0, core_px=0.0))
        probe_result = probe.run(duration=90.0)
        row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        start = probe_result.full_burst_ends[2]
        next_b1 = next(
            t for t, _actor, stage in probe_result.casts
            if t > start + 1e-9 and stage == '1'
        )
        self.assertLess(next_b1, start + 10.0)
        runtime = BurstRuntime(compiled, policy, EnemyStaticProfile(duration=90.0, core_px=0.0))
        runtime.run(duration=next_b1 + 1e-5)
        self.assertTrue(runtime.dispatcher.effects.has_named_state(row.actor, '숙취', now=next_b1))
        self.assertEqual(runtime.dispatcher.effects.named_stack(row.actor, '취기', now=next_b1), 1.0)
        for passive_id in row.passive_effect_ids:
            passive = compiled.effects[passive_id]
            self.assertTrue(any(
                active.effect_id == passive.effect_id and active.active(next_b1)
                for active in runtime.dispatcher.effects._active.values()
            ))
        self.assertAlmostEqual(
            runtime.dispatcher.control_block_until(row.actor, next_b1),
            start + 10.0,
            places=9,
        )

    def test_generic_rapid_block_is_half_open_no_catchup_and_no_per_shot_events(self):
        _moris, compiled = self._compiled('레이드_루주')
        row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        state = StateStore.from_compiled_squad(compiled)
        effects = ActiveEffectStore(compiled, state)
        scheduler = EventScheduler()
        runtime = DynamicRapidCadenceRuntime(
            compiled, effects, state, scheduler, duration=20.0, effect_filter=lambda _e: False
        )
        scored = []
        runtime.attach_score_sink((row.actor,), lambda actor, count, time: scored.append((actor, count, time)))
        runtime.attach_weapon_block_until(
            lambda actor, now: 10.0 if actor == row.actor and 2.0 <= now < 10.0 else None
        )
        runtime.start(0.0)
        runtime.advance_to(1.999, inclusive=True)
        before = sum(count for _actor, count, _time in scored)
        queued_before = len(scheduler)
        runtime.advance_to(9.999, inclusive=True)
        self.assertEqual(sum(count for _actor, count, _time in scored), before)
        runtime.advance_to(10.0, inclusive=True)
        at_end = sum(count for _actor, count, _time in scored)
        self.assertEqual(at_end, before + 1)
        runtime.advance_to(10.2, inclusive=True)
        after = sum(count for _actor, count, _time in scored)
        self.assertLess(after - at_end, 20)
        self.assertEqual(len(scheduler), queued_before)

    def test_existing_reload_completion_is_not_stretched_by_weapon_block(self):
        _moris, compiled = self._compiled('레이드_루주')
        row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        state = StateStore.from_compiled_squad(compiled)
        effects = ActiveEffectStore(compiled, state)
        scheduler = EventScheduler()
        runtime = DynamicRapidCadenceRuntime(
            compiled, effects, state, scheduler, duration=20.0, effect_filter=lambda _e: False
        )
        runtime.attach_score_sink((row.actor,), lambda *_args: None)
        runtime.attach_weapon_block_until(
            lambda actor, now: 12.0 if actor == row.actor and 1.1 <= now < 12.0 else None
        )
        runtime.start(0.0)
        runtime.advance_to(1.0, inclusive=False)
        self.assertTrue(runtime.apply_force_reload((row.actor,), 1.0))
        st = runtime._states[row.actor]
        reload_end = st.phase_end
        runtime.advance_to(reload_end, inclusive=True)
        self.assertEqual(st.phase, 'firing')
        self.assertAlmostEqual(st.phase_end, 12.0, places=9)
        self.assertEqual(st.ammo, runtime._full_ammo(row.actor, reload_end))

    def test_burst_candidate_skips_controlled_actor_or_waits_sparse_to_unblock(self):
        _moris, compiled = self._compiled('레이드_루주')
        row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        alternate = next(
            actor for actor, member in enumerate(compiled.members)
            if actor != row.actor and member.burst_stage == compiled.members[row.actor].burst_stage
        )
        stage = compiled.members[row.actor].burst_stage
        policy = BurstPolicy(
            duration=30.0,
            sequence=({stage: (row.actor, alternate)},),
        )
        machine = BurstMachine(compiled, policy)
        machine.attach_candidate_availability(
            lambda actor, now: not (actor == row.actor and now < 15.0),
            lambda actor, now: 15.0 if actor == row.actor and now < 15.0 else None,
        )
        scheduler = EventScheduler()
        signals = machine._attempt_stage(stage, 5.0, scheduler)
        self.assertTrue(any(sig.source_actor == alternate for sig in signals if sig.event_key == 'burst_cast'))

        policy2 = BurstPolicy(duration=30.0, sequence=({stage: (row.actor,)},))
        machine2 = BurstMachine(compiled, policy2)
        machine2.attach_candidate_availability(
            lambda actor, now: not (actor == row.actor and now < 15.0),
            lambda actor, now: 15.0 if actor == row.actor and now < 15.0 else None,
        )
        scheduler2 = EventScheduler()
        self.assertEqual(machine2._attempt_stage(stage, 5.0, scheduler2), [])
        self.assertAlmostEqual(scheduler2.peek_time(), 15.0, places=9)

    def test_extra_provider_mutator_stun_or_immunity_fail_closed(self):
        _moris, compiled = self._compiled('레이드_루주')
        row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        provider = compiled.effects[row.stack_effect_id]
        control = compiled.effects[row.control_effect_id]
        remover = compiled.effects[row.remover_effect_id]
        next_id = max(effect.effect_id for effect in compiled.effects) + 1

        duplicate = replace(provider, effect_id=next_id, actor=0)
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(self._append(compiled, 0, duplicate)))

        mutator = replace(
            remover,
            effect_id=next_id,
            actor=0,
            name='synthetic mutator',
            stat='buff_stack_remove',
            condition_rules=(),
            triggers=(compile_trigger_rule('full_burst_end'),),
        )
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(self._append(compiled, 0, mutator)))

        other_stun = replace(control, effect_id=next_id, name='synthetic stun')
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(self._append(compiled, row.actor, other_stun)))

        immunity = replace(control, effect_id=next_id, name='synthetic immunity', stat='stun_immune')
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(self._append(compiled, row.actor, immunity)))

    def test_state_end_consumer_and_weapon_control_shape_fail_closed(self):
        _moris, compiled = self._compiled('레이드_루주')
        row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        source = compiled.members[0].effects[0]
        extra = replace(
            source,
            effect_id=max(effect.effect_id for effect in compiled.effects) + 1,
            actor=0,
            name='synthetic state end consumer',
            triggers=(compile_trigger_rule('event:state_end:취기'),),
        )
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(self._append(compiled, 0, extra)))

        member = compiled.members[row.actor]
        weapon = dict(member.weapon)
        weapon['control'] = {'unsupported': True}
        member = replace(member, weapon=weapon)
        guarded = replace(
            compiled,
            members=tuple(member if i == row.actor else other for i, other in enumerate(compiled.members)),
        )
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(guarded))


if __name__ == '__main__':
    unittest.main()
