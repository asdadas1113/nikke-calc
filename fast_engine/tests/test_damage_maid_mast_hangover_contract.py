from __future__ import annotations

from dataclasses import replace
import unittest

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import BurstMachine, BurstPolicy, compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import compile_condition
from fast_engine.engine.control_lifecycle import certified_stack3_self_stun_remove_lifecycles
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.dynamic_rapid import DynamicRapidCadenceRuntime
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.state import StateStore
from fast_engine.engine.targets import TargetMode, TargetSpec


class MaidMastHangoverContractTests(unittest.TestCase):
    PUBLIC = ('레이드_루주', '레이드_브리드디젤')
    MAST = '마스트 : 로망틱 메이드'

    @staticmethod
    def _compiled(label='레이드_루주'):
        moris = spec.build_squad(list(snapshot.SQUADS[label]['members']))
        return moris, compile_moris_squad(moris)

    @staticmethod
    def _replace_effect(compiled, effect_id, replacement):
        members = []
        for member in compiled.members:
            effects = tuple(
                replacement if effect.effect_id == effect_id else effect
                for effect in member.effects
            )
            members.append(replace(member, effects=effects))
        return replace(compiled, members=tuple(members))

    def test_public_moris_oracle_timestamps_and_fast_lifecycle_boundary(self):
        expected_starts = {
            '레이드_루주': 39.4,
            '레이드_브리드디젤': 38.46666666666667,
        }
        for label in self.PUBLIC:
            with self.subTest(label=label):
                moris, compiled = self._compiled(label)
                oracle = simulate(
                    moris,
                    config={
                        'duration': 90.0,
                        'first_burst_time': 3.0,
                        'rng_mode': 'expected',
                    },
                    seed=42,
                    verbose=True,
                )
                log = oracle.log
                self.assertIsNotNone(log)
                assert log is not None
                full_burst_ends = [
                    float(row.t) for row in log.burst_log
                    if row.event == 'full_burst 종료'
                ]
                hangovers = [
                    row for row in log.buff_events
                    if row.caster == self.MAST
                    and row.name == '숙취'
                    and row.kind == 'activate'
                ]
                removals = [
                    row for row in log.buff_events
                    if row.caster == self.MAST
                    and row.name == '취기'
                    and row.kind == 'expire'
                ]
                remover_instants = [
                    row for row in log.instant_events
                    if row.caster == self.MAST
                    and row.name == '파이레츠 스피릿 3'
                ]
                self.assertGreaterEqual(len(hangovers), 1)
                start = float(hangovers[0].t)
                end = float(hangovers[0].expires_at)
                self.assertAlmostEqual(start, expected_starts[label], places=9)
                self.assertAlmostEqual(start, full_burst_ends[2], places=9)
                self.assertAlmostEqual(end, start + 10.0, places=9)
                self.assertAlmostEqual(float(removals[0].t), start, places=9)
                self.assertAlmostEqual(float(remover_instants[0].t), start, places=9)

                normal_hits = sorted(
                    float(hit.t) for hit in oracle.hits
                    if hit.caster == self.MAST and hit.skill_name == '기본 공격'
                )
                self.assertFalse(any(start <= t < end for t in normal_hits))
                first_after = next(t for t in normal_hits if t >= end)
                self.assertGreaterEqual(first_after, end)
                self.assertLessEqual(first_after - end, 1.0 / 60.0 + 1e-8)

                policy = compile_burst_policy(
                    moris, compiled, {'duration': 90.0, 'first_burst_time': 3.0}
                )
                fast = BurstRuntime(
                    compiled, policy, EnemyStaticProfile(duration=90.0, core_px=0.0)
                )
                result = fast.run(duration=90.0)
                fast_start = result.full_burst_ends[2]
                self.assertLessEqual(abs(fast_start - start), 1.0 / 60.0 + 1e-8)

                row = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
                replay = BurstRuntime(
                    compiled, policy, EnemyStaticProfile(duration=90.0, core_px=0.0)
                )
                replay.run(duration=fast_start + 1e-6)
                self.assertAlmostEqual(
                    replay.dispatcher.control_block_until(row.actor, fast_start + 1e-7),
                    fast_start + 10.0,
                    places=9,
                )
                self.assertIsNone(
                    replay.dispatcher.control_block_until(row.actor, fast_start + 10.0)
                )

    def test_finite_reference_capture_survives_named_source_removal(self):
        _moris, compiled = self._compiled('레이드_루주')
        owned = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        actor = owned.actor
        provider = compiled.effects[owned.stack_effect_id]
        finite = next(
            effect for effect in compiled.members[actor].effects
            if effect.name == '파이레츠 스피릿 2'
        )
        state = StateStore.from_compiled_squad(compiled)
        effects = ActiveEffectStore(compiled, state)
        effects.enable_finite_reference_stack_capture((finite.effect_id,))
        scheduler = EventScheduler()

        for now in (0.0, 1.0, 2.0):
            effects.activate(provider, actor, now, scheduler)
        self.assertEqual(effects.named_stack(actor, '취기', now=2.0), 3.0)

        actives = effects.activate_group(
            finite, tuple(range(len(compiled.members))), 3.0, scheduler
        )
        self.assertTrue(actives)
        self.assertTrue(all(active.scaling_stack == 3.0 for active in actives))
        expires = {active.expires_at for active in actives}
        self.assertEqual(expires, {13.0})

        self.assertTrue(effects.remove_named_state(actor, '취기', now=4.0))
        self.assertFalse(effects.has_named_state(actor, '취기', now=4.0))
        for active in actives:
            self.assertTrue(active.active(12.999999))
            self.assertEqual(effects.effect_value_scale(finite, active, now=12.0), 3.0)
            self.assertFalse(active.active(13.0))

    def test_mg_warmup_ammo_and_no_catchup_across_half_open_block(self):
        _moris, compiled = self._compiled('레이드_루주')
        owned = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        actor = owned.actor
        state = StateStore.from_compiled_squad(compiled)
        effects = ActiveEffectStore(compiled, state)
        scheduler = EventScheduler()
        runtime = DynamicRapidCadenceRuntime(
            compiled, effects, state, scheduler,
            duration=6.0,
            effect_filter=lambda _effect: False,
        )
        scored = []
        runtime.attach_score_sink(
            (actor,), lambda a, count, t: scored.append((a, count, t))
        )
        runtime.attach_weapon_block_until(
            lambda a, now: 3.0 if a == actor and 1.0 <= now < 3.0 else None
        )
        runtime.start(0.0)
        runtime.advance_to(0.999, inclusive=True)
        st = runtime._states[actor]
        ammo_before = st.ammo
        warmup_before = st.warmup
        shots_before = sum(count for _a, count, _t in scored)
        self.assertGreater(warmup_before, 1.0)

        runtime.advance_to(2.999999, inclusive=True)
        self.assertEqual(st.ammo, ammo_before)
        self.assertEqual(sum(count for _a, count, _t in scored), shots_before)

        runtime.advance_to(3.0, inclusive=True)
        self.assertEqual(st.ammo, ammo_before - 1)
        self.assertEqual(sum(count for _a, count, _t in scored), shots_before + 1)
        self.assertLessEqual(st.warmup, 1.000001)

    def test_all_controlled_candidates_wait_for_earliest_unblock(self):
        _moris, compiled = self._compiled('레이드_루주')
        owned = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        actor = owned.actor
        alternate = next(
            a for a, member in enumerate(compiled.members)
            if a != actor and member.burst_stage == compiled.members[actor].burst_stage
        )
        stage = compiled.members[actor].burst_stage
        policy = BurstPolicy(duration=30.0, sequence=({stage: (actor, alternate)},))
        machine = BurstMachine(compiled, policy)
        unblock = {actor: 16.0, alternate: 15.0}
        machine.attach_candidate_availability(
            lambda a, now: now >= unblock[a],
            lambda a, now: unblock[a] if now < unblock[a] else None,
        )
        scheduler = EventScheduler()
        self.assertEqual(machine._attempt_stage(stage, 5.0, scheduler), [])
        self.assertAlmostEqual(scheduler.peek_time(), 15.0, places=9)

    def test_ambiguous_target_or_condition_and_standalone_families_fail_closed(self):
        _moris, compiled = self._compiled('레이드_루주')
        owned = certified_stack3_self_stun_remove_lifecycles(compiled)[0]
        control = compiled.effects[owned.control_effect_id]
        remover = compiled.effects[owned.remover_effect_id]

        ambiguous_target = replace(
            control,
            target='synthetic ambiguous',
            target_spec=TargetSpec('synthetic ambiguous', TargetMode.UNSUPPORTED),
        )
        guarded = self._replace_effect(compiled, control.effect_id, ambiguous_target)
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(guarded))
        guarded_dispatcher = TriggerDispatcher(guarded)
        self.assertFalse(guarded_dispatcher.is_runtime_executable_effect(ambiguous_target))

        ambiguous_condition = replace(
            control,
            conditions=control.conditions + ('during_full_burst',),
            condition_rules=control.condition_rules + (compile_condition('during_full_burst'),),
        )
        guarded = self._replace_effect(compiled, control.effect_id, ambiguous_condition)
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(guarded))
        guarded_dispatcher = TriggerDispatcher(guarded)
        self.assertFalse(guarded_dispatcher.is_runtime_executable_effect(ambiguous_condition))

        standalone_stun = replace(control, name='synthetic standalone stun')
        guarded = self._replace_effect(compiled, control.effect_id, standalone_stun)
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(guarded))
        guarded_dispatcher = TriggerDispatcher(guarded)
        self.assertFalse(guarded_dispatcher.is_runtime_executable_effect(standalone_stun))

        standalone_remove = replace(remover, name='synthetic standalone remove')
        guarded = self._replace_effect(compiled, remover.effect_id, standalone_remove)
        self.assertFalse(certified_stack3_self_stun_remove_lifecycles(guarded))
        guarded_dispatcher = TriggerDispatcher(guarded)
        self.assertFalse(guarded_dispatcher.is_runtime_executable_effect(standalone_remove))


if __name__ == '__main__':
    unittest.main()
