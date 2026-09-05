from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.model import CompiledSquad
from fast_engine.engine.score import static_score_blockers
from fast_engine.engine.target_scope import possible_ally_targets
from fast_engine.engine.triggers import TriggerIndex


class StatAppliedChargeSpeedTests(unittest.TestCase):
    @staticmethod
    def _public():
        moris_squad = spec.build_squad(
            list(snapshot.SQUADS["레이드_앨리스브래디"]["members"])
        )
        squad = compile_moris_squad(moris_squad)
        brady = next(i for i, member in enumerate(squad.members) if member.name == "브래디")
        return moris_squad, squad, brady

    def test_public_brady_certifies_only_reachable_split_branch(self) -> None:
        _moris, squad, brady = self._public()
        stay = next(e for e in squad.members[brady].effects if e.name == "머물고 싶은 맛")
        split = next(e for e in squad.members[brady].effects if e.name == "나누고 싶은 맛")
        stay_remove = next(e for e in squad.members[brady].effects if e.name == "머물고 싶은 맛 2")
        split_remove = next(e for e in squad.members[brady].effects if e.name == "나누고 싶은 맛 2")

        self.assertTrue(TriggerDispatcher._stat_applied_charge_speed_shape_supported(stay))
        self.assertTrue(TriggerDispatcher._stat_applied_charge_speed_shape_supported(split))
        self.assertFalse(
            TriggerDispatcher.stat_applied_dependency_score_safe(
                squad, stay, "event:stat_applied:dot_dmg_pct"
            )
        )
        # Maid Mast's finite reference-stack split_dmg_pct provider is now
        # owned, so this exact downstream stat_applied branch is reachable.
        self.assertTrue(
            TriggerDispatcher.stat_applied_dependency_score_safe(
                squad, split, "event:stat_applied:split_dmg_pct"
            )
        )
        self.assertFalse(TriggerDispatcher.is_executable_effect(stay_remove))
        self.assertFalse(TriggerDispatcher.is_executable_effect(split_remove))

        blockers = set(static_score_blockers(squad))
        self.assertIn("cadence:브래디:머물고 싶은 맛:charge_speed_pct", blockers)
        self.assertNotIn("cadence:브래디:나누고 싶은 맛:charge_speed_pct", blockers)

        seen: set[tuple[str, ...]] = set()
        cadence = 0
        certified = 0
        matches: set[tuple[str, str, str]] = set()
        for name, entry in snapshot.SQUADS.items():
            if name.startswith("지그_"):
                continue
            members = tuple(entry["members"])
            if members in seen:
                continue
            seen.add(members)
            compiled = compile_moris_squad(spec.build_squad(list(members)))
            rows = static_score_blockers(compiled)
            cadence += sum(row.startswith("cadence:") for row in rows)
            certified += not rows
            for effect in compiled.effects:
                if not TriggerDispatcher._stat_applied_charge_speed_shape_supported(effect):
                    continue
                key = effect.triggers[0].event_key or ""
                if TriggerDispatcher.stat_applied_dependency_score_safe(compiled, effect, key):
                    matches.add((compiled.members[effect.actor].name, effect.name, key))

        self.assertEqual(len(seen), 23)
        self.assertEqual(certified, 2)
        self.assertEqual(cadence, 59)
        self.assertEqual(
            matches,
            {("브래디", "나누고 싶은 맛", "event:stat_applied:split_dmg_pct")},
        )

    def test_fast_stat_applied_activation_sequence_matches_moris(self) -> None:
        moris_squad, squad, brady = self._public()
        stay = next(e for e in squad.members[brady].effects if e.name == "머물고 싶은 맛")
        split = next(e for e in squad.members[brady].effects if e.name == "나누고 싶은 맛")
        fast_split: list[float] = []
        fast_stay: list[float] = []
        original_activate = ActiveEffectStore.activate_group

        def traced_activate(store, effect, targets, now, scheduler):
            if effect.effect_id == split.effect_id:
                fast_split.append(float(now))
            if effect.effect_id == stay.effect_id:
                fast_stay.append(float(now))
            return original_activate(store, effect, targets, now, scheduler)

        duration = 40.0
        policy = compile_burst_policy(moris_squad, squad, {"duration": duration})
        with patch.object(ActiveEffectStore, "activate_group", new=traced_activate):
            BurstRuntime(squad, policy).run(duration=duration)

        moris = simulate(
            moris_squad,
            config={"duration": duration, "rng_mode": "expected"},
            verbose=True,
        )
        moris_split = [
            float(row.t) for row in moris.log.buff_events if row.name == "나누고 싶은 맛"
        ]
        self.assertFalse(fast_stay)
        self.assertEqual(fast_split, moris_split)
        self.assertEqual(len(moris_split), 5)
        blockers = static_score_blockers(squad)
        self.assertNotIn(
            "cadence:브래디:나누고 싶은 맛:charge_speed_pct", blockers
        )
        self.assertIn(
            "cadence:브래디:머물고 싶은 맛:charge_speed_pct", blockers
        )

    def test_opposite_stat_source_keeps_not_self_state_branch_fail_closed(self) -> None:
        _moris, squad, brady = self._public()
        source = next(
            effect
            for effect in squad.effects
            if effect.stat == "split_dmg_pct" and brady in possible_ally_targets(squad, effect)
        )
        members = list(squad.members)
        members[source.actor] = replace(
            members[source.actor],
            effects=tuple(
                replace(effect, stat="dot_dmg_pct")
                if effect.effect_id == source.effect_id
                else effect
                for effect in members[source.actor].effects
            ),
        )
        all_effects = tuple(effect for member in members for effect in member.effects)
        opposite = CompiledSquad(
            tuple(members), TriggerIndex.from_effects(all_effects, actor_count=len(members))
        )
        split = next(e for e in opposite.members[brady].effects if e.name == "나누고 싶은 맛")
        self.assertFalse(
            TriggerDispatcher.stat_applied_dependency_score_safe(
                opposite, split, "event:stat_applied:split_dmg_pct"
            )
        )

    def test_neighboring_stat_applied_shapes_remain_fail_closed(self) -> None:
        _moris, squad, brady = self._public()
        split = next(e for e in squad.members[brady].effects if e.name == "나누고 싶은 맛")
        rule = split.triggers[0]

        self.assertFalse(
            TriggerDispatcher._stat_applied_charge_speed_shape_supported(
                replace(split, duration=None)
            )
        )
        self.assertFalse(
            TriggerDispatcher._stat_applied_charge_speed_shape_supported(
                replace(split, max_stack=2)
            )
        )
        self.assertFalse(
            TriggerDispatcher._stat_applied_charge_speed_shape_supported(
                replace(split, value=-100.0)
            )
        )
        self.assertFalse(
            TriggerDispatcher._stat_applied_charge_speed_shape_supported(
                replace(split, triggers=(replace(rule, event_key="event:stat_applied:atk_pct"),))
            )
        )


if __name__ == "__main__":
    unittest.main()
