from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


p = Path('fast_engine/engine/dispatcher.py')
s = p.read_text(encoding='utf-8')
old = '''    def _self_stack_remove_runtime_supported(self, effect: "CompiledEffect") -> bool:\n        return (\n            self._self_stack_remove_shape_supported(effect)\n            and self._stack_reach_source_shape_supported(self.squad, effect)\n        )\n\n'''
new = old + '''    @classmethod\n    def _full_burst_end_self_direct_remove_dependency_supported(\n        cls, squad: "CompiledSquad", effect: "CompiledEffect"\n    ) -> bool:\n        """Own one unambiguous permanent self provider/remover transaction.\n\n        Moris removes every active row sharing ``target_effect`` by name. Fast's\n        first score-bearing remover slice therefore requires one globally unique\n        provider on the same actor/self cohort. The provider is a permanent\n        one-stack burst-cast ``atk_dmg_pct`` state and the remover is an\n        unconditional full-burst-end event. Any consumer that can observe the\n        provider's removal keeps the pair fail-closed.\n        """\n        name = effect.parameters.get("target_effect")\n        if not (\n            effect.effect_type == "instant"\n            and (effect.stat or "") == "remove_named_buff"\n            and effect.target_spec.mode is TargetMode.SELF\n            and effect.target_spec.runtime_supported\n            and effect.value is None\n            and effect.duration is None\n            and effect.max_stack is None\n            and effect.max_trigger is None\n            and effect.tick_interval is None\n            and isinstance(name, str)\n            and bool(name)\n            and set(effect.parameters) == {"target_effect"}\n            and not effect.condition_rules\n            and len(effect.triggers) == 1\n            and effect.triggers[0].mode is TriggerMode.EVENT\n            and effect.triggers[0].event_key == "full_burst_end"\n        ):\n            return False\n\n        providers = tuple(\n            provider\n            for provider in squad.effects\n            if provider.effect_id != effect.effect_id and provider.name == name\n        )\n        if len(providers) != 1:\n            return False\n        provider = providers[0]\n        if not (\n            provider.actor == effect.actor\n            and provider.effect_type == "buff"\n            and (provider.stat or "") == "atk_dmg_pct"\n            and provider.target_spec.mode is TargetMode.SELF\n            and provider.target_spec.runtime_supported\n            and provider.value is not None\n            and provider.duration in (None, -1, -1.0)\n            and provider.max_stack in (None, 1, 1.0)\n            and provider.max_trigger is None\n            and provider.tick_interval is None\n            and not provider.parameters\n            and not provider.condition_rules\n            and len(provider.triggers) == 1\n            and provider.triggers[0].mode is TriggerMode.EVENT\n            and provider.triggers[0].event_key == "burst_cast"\n            and is_direct_damage_buff_runtime_supported(provider)\n            and cls.is_executable_effect(provider)\n        ):\n            return False\n\n        state_end_key = f"event:state_end:{name}"\n        if any(\n            other.effect_id != effect.effect_id\n            and any((rule.event_key or "") == state_end_key for rule in other.triggers)\n            for other in squad.effects\n        ):\n            return False\n        if any(\n            other.effect_id != effect.effect_id\n            and any(rule.key == name for rule in other.condition_rules)\n            for other in squad.effects\n        ):\n            return False\n        if any(\n            other.effect_id != effect.effect_id\n            and (\n                other.parameters.get("target_effect") == name\n                or other.parameters.get("scaling_ref") == name\n            )\n            for other in squad.effects\n        ):\n            return False\n        return True\n\n'''
s = replace_once(s, old, new, 'dispatcher helper')
old = '''        if self._enemy_remove_named_state_runtime_supported(effect):\n            return True\n        family = self._gauge_family(effect)\n'''
new = '''        if self._enemy_remove_named_state_runtime_supported(effect):\n            return True\n        if self._full_burst_end_self_direct_remove_dependency_supported(self.squad, effect):\n            return True\n        family = self._gauge_family(effect)\n'''
s = replace_once(s, old, new, 'runtime executable')
old = '''            elif stat == "remove_named_buff" and self._enemy_remove_named_state_runtime_supported(effect):\n                name = str(effect.parameters.get("target_effect") or "")\n                if tuple(targets) != (ENEMY,):\n                    return False\n                self.effects.remove_named_state(ENEMY, name, now=now)\n            elif stat in self._GAUGE_STATS:\n'''
new = '''            elif stat == "remove_named_buff" and self._enemy_remove_named_state_runtime_supported(effect):\n                name = str(effect.parameters.get("target_effect") or "")\n                if tuple(targets) != (ENEMY,):\n                    return False\n                self.effects.remove_named_state(ENEMY, name, now=now)\n            elif (\n                stat == "remove_named_buff"\n                and self._full_burst_end_self_direct_remove_dependency_supported(self.squad, effect)\n            ):\n                name = str(effect.parameters.get("target_effect") or "")\n                if tuple(targets) != (effect.actor,):\n                    return False\n                self.effects.remove_named_state(effect.actor, name, now=now)\n            elif stat in self._GAUGE_STATS:\n'''
s = replace_once(s, old, new, 'instant remover')
p.write_text(s, encoding='utf-8')

p = Path('fast_engine/engine/score.py')
s = p.read_text(encoding='utf-8')
old = '''    if _is_patternless_unreachable(effect):\n        return False\n    if damage_sink.supports_state_operation(effect):\n        return False\n'''
new = '''    if _is_patternless_unreachable(effect):\n        return False\n    if TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(\n        squad, effect\n    ):\n        return False\n    if damage_sink.supports_state_operation(effect):\n        return False\n'''
s = replace_once(s, old, new, 'score remover guard')
p.write_text(s, encoding='utf-8')

Path('fast_engine/tests/test_damage_named_remove_dependency.py').write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import BurstMachine, BurstSignal, compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.conditions import compile_condition
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.scheduler import EventScheduler
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.state import StateStore
from fast_engine.engine.targets import TargetMode


class NamedRemoveDependencyTests(unittest.TestCase):
    def _fixture(self):
        members = list(snapshot.SQUADS['스쿼드3']['members'])
        squad = spec.build_squad(members)
        compiled = compile_moris_squad(squad)
        actor = members.index('아르카나 : 포츈 메이트')
        remover = next(e for e in compiled.members[actor].effects if e.name == '쌓여가는 사진첩 3')
        blocked_neighbor = next(e for e in compiled.members[actor].effects if e.name == '쌓여가는 사진첩 2')
        provider = next(e for e in compiled.members[actor].effects if e.name == '추억 남기기 3')
        return squad, compiled, actor, remover, blocked_neighbor, provider

    @staticmethod
    def _replace_actor_effects(compiled, actor, effects):
        member = replace(compiled.members[actor], effects=tuple(effects))
        members = tuple(member if i == actor else row for i, row in enumerate(compiled.members))
        return replace(compiled, members=members)

    def test_real_arcana_atk_damage_pair_is_owned_but_state_machine_neighbor_is_not(self):
        _squad, compiled, _actor, remover, blocked_neighbor, _provider = self._fixture()
        self.assertTrue(TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(compiled, remover))
        self.assertFalse(TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported(compiled, blocked_neighbor))
        blockers = set(static_score_blockers(compiled))
        self.assertNotIn(
            'normal_state:아르카나 : 포츈 메이트:쌓여가는 사진첩 3:remove_named_buff', blockers
        )
        self.assertIn(
            'normal_state:아르카나 : 포츈 메이트:쌓여가는 사진첩 2:remove_named_buff', blockers
        )
        self.assertTrue(any('아르카나 : 포츈 메이트' in b for b in blockers))

    def test_dispatcher_removes_at_full_burst_end_and_next_burst_reactivates(self):
        squad, compiled, actor, remover, blocked_neighbor, provider = self._fixture()
        policy = compile_burst_policy(squad, compiled, {'duration': 30.0, 'first_burst_time': 3.0})
        state = StateStore.from_compiled_squad(compiled)
        scheduler = EventScheduler()
        dispatcher = TriggerDispatcher(
            compiled, state, EnemyStaticProfile(duration=30.0),
            BurstMachine(compiled, policy), scheduler,
        )
        self.assertTrue(dispatcher.can_activate_effect(remover))
        self.assertFalse(dispatcher.can_activate_effect(blocked_neighbor))
        name = provider.name
        for cast_t, end_t in ((3.2, 13.4), (15.7333333333, 25.9333333333)):
            dispatcher.dispatch(BurstSignal(cast_t, 'burst_cast', actor, actor))
            self.assertTrue(dispatcher.effects.has_named_state(actor, name, now=cast_t))
            dispatcher.dispatch(BurstSignal(end_t, 'full_burst_end', actor, actor))
            self.assertFalse(dispatcher.effects.has_named_state(actor, name, now=end_t))

    def test_moris_removes_exactly_on_full_burst_end_without_frame_delay(self):
        squad, _compiled, _actor, _remover, _blocked_neighbor, _provider = self._fixture()
        result = simulate(
            squad,
            config={'duration': 30.0, 'first_burst_time': 3.0, 'rng_mode': 'expected'},
            seed=42,
            verbose=True,
        )
        ends = [float(row.t) for row in result.log.burst_log if row.event == 'full_burst 종료']
        expiries = [
            float(row.t) for row in result.log.buff_events
            if row.name == '추억 남기기 3' and row.kind == 'expire'
        ]
        self.assertEqual(expiries, ends)

    def test_neighboring_or_ambiguous_shapes_remain_fail_closed(self):
        _squad, compiled, actor, remover, _blocked_neighbor, provider = self._fixture()
        helper = TriggerDispatcher._full_burst_end_self_direct_remove_dependency_supported
        self.assertFalse(helper(compiled, replace(
            remover, target_spec=replace(remover.target_spec, mode=TargetMode.ENEMY)
        )))
        self.assertFalse(helper(compiled, replace(
            remover,
            conditions=('during_full_burst',),
            condition_rules=(compile_condition('during_full_burst'),),
        )))
        self.assertFalse(helper(compiled, replace(
            remover,
            triggers=(replace(remover.triggers[0], raw='on_attack', event_key='on_attack'),),
        )))

        effects = list(compiled.members[actor].effects)
        finite = replace(provider, duration=10.0)
        finite_effects = [finite if e.effect_id == provider.effect_id else e for e in effects]
        self.assertFalse(helper(self._replace_actor_effects(compiled, actor, finite_effects), remover))

        duplicate = replace(provider, effect_id=max(e.effect_id for e in compiled.effects) + 1)
        self.assertFalse(helper(
            self._replace_actor_effects(compiled, actor, effects + [duplicate]), remover
        ))

        consumer = replace(
            provider,
            effect_id=max(e.effect_id for e in compiled.effects) + 2,
            name='synthetic consumer',
            stat='atk_pct',
            conditions=('self_state:추억 남기기 3',),
            condition_rules=(compile_condition('self_state:추억 남기기 3'),),
        )
        self.assertFalse(helper(
            self._replace_actor_effects(compiled, actor, effects + [consumer]), remover
        ))


if __name__ == '__main__':
    unittest.main()
''', encoding='utf-8')
