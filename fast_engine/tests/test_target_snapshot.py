from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.targets import compile_target


class TargetSnapshotTests(unittest.TestCase):
    def _runtime(self) -> BurstRuntime:
        names = ["리타", "크라운", "홍련", "앨리스", "나가"]
        moris_squad = build_squad(names)
        compiled = compile_moris_squad(moris_squad)
        policy = compile_burst_policy(moris_squad, compiled, {"duration": 10.0})
        return BurstRuntime(compiled, policy)

    def test_same_caster_time_and_rank_target_share_one_cohort(self):
        runtime = self._runtime()
        resolver = runtime.dispatcher.targets
        actor_by_name = {
            member.name: actor for actor, member in enumerate(runtime.squad.members)
        }
        spec = compile_target("allies_lowest_hp:1", actor_by_name=actor_by_name)

        runtime.state.set_hp(1, runtime.squad.members[1].base_hp * 0.50)
        first = resolver.resolve(spec, owner_actor=0, now=5.0)
        self.assertEqual(first, (1,))

        # Another same-frame mutation would normally change the ranking. Moris'
        # lazy target cache shares the first selected cohort between effects from
        # the same caster/time/raw target, so Fast must keep actor 1 here.
        runtime.state.set_hp(2, runtime.squad.members[2].base_hp * 0.10)
        same_activation = resolver.resolve(spec, owner_actor=0, now=5.0)
        self.assertEqual(same_activation, first)

        # A new activation time gets a fresh snapshot.
        next_activation = resolver.resolve(spec, owner_actor=0, now=5.1)
        self.assertEqual(next_activation, (2,))

    def test_lazy_selection_identity_uses_activation_time_but_live_rank_state(self):
        runtime = self._runtime()
        resolver = runtime.dispatcher.targets
        actor_by_name = {
            member.name: actor for actor, member in enumerate(runtime.squad.members)
        }
        spec = compile_target("allies_top_atk:1", actor_by_name=actor_by_name)

        first = resolver.resolve(
            spec, owner_actor=0, now=5.1, selection_time=5.0
        )
        # A later read of the same activation keeps the already chosen cohort,
        # even though its wall-clock query time changed.
        runtime.dispatcher.effects.activate(
            next(
                e for e in runtime.squad.effects
                if e.effect_type == "buff" and (e.stat or "") == "atk_pct"
                and e.target_spec.mode.value == "self"
            ),
            1,
            5.15,
            runtime.scheduler,
        )
        same = resolver.resolve(
            spec, owner_actor=0, now=5.2, selection_time=5.0
        )
        self.assertEqual(same, first)

    def test_lowest_atk_burst3_uses_base_stage_and_effective_atk(self):
        runtime = self._runtime()
        resolver = runtime.dispatcher.targets
        actor_by_name = {
            member.name: actor for actor, member in enumerate(runtime.squad.members)
        }
        spec = compile_target("allies_lowest_atk_burst3:1", actor_by_name=actor_by_name)

        candidates = [
            actor
            for actor, member in enumerate(runtime.squad.members)
            if member.burst_stage == "3"
        ]
        self.assertGreaterEqual(len(candidates), 2)
        expected = min(
            candidates,
            key=lambda actor: (runtime.dispatcher.effects.effective_atk(actor, now=1.0), actor),
        )

        # Moris filters by parsed/base B3, so a live stage override must not
        # remove the actor from this particular target selector.
        runtime.machine.set_stage_override(expected, "1")
        self.assertEqual(
            resolver.resolve(spec, owner_actor=0, now=1.0),
            (expected,),
        )


if __name__ == "__main__":
    unittest.main()
