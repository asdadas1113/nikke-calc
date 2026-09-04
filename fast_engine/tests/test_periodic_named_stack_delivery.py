from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from context.spec import build_squad
from fast_engine.engine.burst import BurstPolicy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.frame_lattice import moris_observed_tick
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.targets import TargetMode
from fast_engine.engine.triggers import TriggerIndex, compile_trigger_rule


class PeriodicNamedStackDeliveryTests(unittest.TestCase):
    NAMES = (
        "미란다",
        "브리드 : 사일런트 트랙",
        "헬름",
        "루주",
        "나유타",
    )
    NAYUTA = 4
    CONSUMERS = ("위선", "위선 2", "무상", "무상 2", "무상 3")

    @classmethod
    def _compiled(cls):
        return compile_moris_squad(build_squad(list(cls.NAMES)))

    @classmethod
    def _provider(cls, squad):
        return next(
            effect
            for effect in squad.members[cls.NAYUTA].effects
            if effect.name == "기억 흡수"
        )

    def test_narrow_periodic_permanent_self_stack_shape(self):
        squad = self._compiled()
        provider = self._provider(squad)
        helper = TriggerDispatcher._periodic_permanent_self_direct_stack_shape_supported
        self.assertTrue(helper(provider))

        all_allies = next(
            effect for effect in squad.members[self.NAYUTA].effects
            if effect.name == "위선"
        )
        conditional = next(
            effect for effect in squad.members[self.NAYUTA].effects
            if effect.name == "무상"
        )
        unsafe = (
            replace(provider, duration=5.0),
            replace(provider, polarity="beneficial"),
            replace(provider, max_stack=1.0),
            replace(provider, max_trigger=1),
            replace(provider, tick_interval=1.0),
            replace(provider, parameters={"note": "mutable"}),
            replace(
                provider,
                target=all_allies.target,
                target_spec=all_allies.target_spec,
            ),
            replace(
                provider,
                conditions=conditional.conditions,
                condition_rules=conditional.condition_rules,
            ),
        )
        self.assertTrue(all(not helper(effect) for effect in unsafe))

    def test_named_event_consumers_see_post_stack_state_and_refresh_after_cap(self):
        squad = self._compiled()
        duration = 100.0
        rows: list[tuple[float, int, tuple[str, ...]]] = []
        original_dispatch = TriggerDispatcher.dispatch

        def dispatch(dispatcher, signal, **kwargs):
            result = original_dispatch(dispatcher, signal, **kwargs)
            if (
                signal.owner_actor == self.NAYUTA
                and signal.event_key == "event:기억 흡수"
            ):
                stack = int(round(dispatcher.effects.named_stack(
                    self.NAYUTA, "기억 흡수", now=signal.time
                )))
                active = tuple(
                    name
                    for name in self.CONSUMERS
                    if dispatcher.effects.named_stack(
                        self.NAYUTA, name, now=signal.time
                    ) > 0.0
                )
                rows.append((float(signal.time), stack, active))
            return result

        runtime = BurstRuntime(
            squad,
            BurstPolicy(
                duration=duration,
                no_burst_actors=frozenset(range(len(squad.members))),
            ),
            EnemyStaticProfile(duration=duration),
        )
        with patch.object(TriggerDispatcher, "dispatch", new=dispatch):
            runtime.run(duration=duration)

        expected_times = tuple(
            moris_observed_tick(float(n), horizon=duration)
            for n in range(3, 100, 3)
        )
        self.assertEqual(len(rows), len(expected_times))
        for row, expected in zip(rows, expected_times):
            self.assertAlmostEqual(row[0], expected, places=12)

        self.assertEqual(rows[0][1:], (1, ("위선", "위선 2")))
        self.assertEqual(rows[1][1:], (2, ("위선", "위선 2", "무상")))
        self.assertEqual(
            rows[9][1:],
            (10, ("위선", "위선 2", "무상", "무상 2")),
        )
        self.assertEqual(
            rows[29][1:],
            (30, ("위선", "위선 2", "무상", "무상 2", "무상 3")),
        )
        self.assertEqual(rows[30][1], 30)
        self.assertEqual(rows[30][2], rows[29][2])

    def test_public_nayuta_delivery_opens_but_weapon_change_stays_closed(self):
        rosters = (
            ("츠바이", "나유타", "프리바티", "스노우 화이트 : 헤비암즈", "리틀 머메이드"),
            ("리틀 머메이드", "벨벳", "나유타", "네온 : 비전 아이", "리버렐리오"),
            ("토브", "나유타", "소다 : 트윙클링 바니", "도로시 : 세렌디피티", "드레이크"),
        )
        for names in rosters:
            with self.subTest(names=names):
                blockers = static_score_blockers(
                    compile_moris_squad(build_squad(list(names)))
                )
                nayuta_delivery = tuple(
                    blocker
                    for blocker in blockers
                    if blocker.startswith("normal_delivery:나유타:")
                    or blocker.startswith("skill_state_delivery:나유타:")
                )
                self.assertEqual(nayuta_delivery, ())
                self.assertIn("weapon_change:나유타:기억 연소", blockers)

    def test_live_periodic_accuracy_still_invalidates_static_core_count_plan(self):
        squad = self._compiled()
        owner = squad.members[self.NAYUTA]
        base = next(effect for effect in owner.effects if effect.name == "무상")
        core_observer = replace(
            base,
            name="synthetic core observer",
            stat="atk_pct",
            triggers=(compile_trigger_rule("core_hit_count:3"),),
            conditions=(),
            condition_rules=(),
            target="self",
            target_spec=replace(base.target_spec, mode=TargetMode.SELF),
            duration=5.0,
            max_stack=1.0,
            max_trigger=None,
            tick_interval=None,
            parameters={},
        )
        members = list(squad.members)
        members[self.NAYUTA] = replace(
            owner,
            effects=tuple(
                core_observer if effect.effect_id == base.effect_id else effect
                for effect in owner.effects
            ),
        )
        effects = tuple(effect for member in members for effect in member.effects)
        mutated = CompiledSquad(
            tuple(members),
            TriggerIndex.from_effects(effects, actor_count=len(members)),
        )
        duration = 10.0
        runtime = BurstRuntime(
            mutated,
            BurstPolicy(
                duration=duration,
                no_burst_actors=frozenset(range(len(mutated.members))),
            ),
            EnemyStaticProfile(
                duration=duration,
                core_uptime=1.0,
                core_px=10.0,
            ),
        )
        with self.assertRaisesRegex(NotImplementedError, "기억 흡수"):
            runtime.start(duration=duration)


if __name__ == "__main__":
    unittest.main()
