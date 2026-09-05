from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from calculator.timeline import simulate
from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.damage_policy import is_direct_damage_buff_runtime_supported
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.score import static_score_blockers


class FullChargeHitBulletLifetimeTests(unittest.TestCase):
    BLOCKER = "normal_delivery:D : 킬러 와이프:캄 스나이핑:pierce_enabled"

    @staticmethod
    def _fixture():
        team, entry = next(
            (name, entry)
            for name, entry in snapshot.SQUADS.items()
            if not name.startswith("지그_") and "D : 킬러 와이프" in entry["members"]
        )
        moris = spec.build_squad(list(entry["members"]))
        compiled = compile_moris_squad(moris)
        actor = next(
            i for i, member in enumerate(compiled.members)
            if member.name == "D : 킬러 와이프"
        )
        effect = next(
            effect for effect in compiled.members[actor].effects
            if effect.name == "캄 스나이핑"
        )
        return team, moris, compiled, actor, effect

    def test_real_d_shape_is_certified_without_broadening_neighbor_events(self):
        _team, _moris, compiled, _actor, effect = self._fixture()
        self.assertEqual(effect.stat, "pierce_enabled")
        self.assertEqual(effect.parameters.get("duration_bullets"), 1)
        self.assertTrue(is_direct_damage_buff_runtime_supported(effect))
        self.assertNotIn(self.BLOCKER, static_score_blockers(compiled))

        base_rule = effect.triggers[0]
        self.assertEqual(base_rule.event_key, "full_charge_hit")
        self.assertTrue(base_rule.trigger_count_reducible)
        for event_key in ("on_attack", "hit_count", "last_bullet", "last_bullet_fire"):
            neighbor = replace(
                effect,
                triggers=(replace(base_rule, event_key=event_key, raw=event_key),),
            )
            self.assertFalse(
                is_direct_damage_buff_runtime_supported(neighbor),
                msg=f"neighboring weapon event unexpectedly opened: {event_key}",
            )

    def test_fast_activation_matches_moris_and_lifetime_consumes_on_next_shot(self):
        _team, moris_squad, compiled, actor, effect = self._fixture()
        duration = 12.0
        policy = compile_burst_policy(
            moris_squad,
            compiled,
            {"duration": duration, "rng_mode": "expected"},
        )

        activations: list[float] = []
        removals: list[float] = []
        shots: list[float] = []
        original_activate = ActiveEffectStore.activate_group
        original_consume = ActiveEffectStore.consume_dynamic_bullet

        def traced_activate(store, candidate, targets, now, scheduler):
            result = original_activate(store, candidate, targets, now, scheduler)
            if candidate.effect_id == effect.effect_id and result:
                activations.append(float(now))
            return result

        def traced_consume(store, owner, now, count=1):
            removed = original_consume(store, owner, now=now, count=count)
            if effect.effect_id in removed:
                removals.append(float(now))
            return removed

        runtime = BurstRuntime(compiled, policy)
        runtime.weapons.attach_score_shot_sink(
            (actor,),
            lambda shot_actor, now: shots.append(float(now)) if shot_actor == actor else None,
        )
        with patch.object(
            ActiveEffectStore,
            "activate_group",
            new=traced_activate,
        ), patch.object(
            ActiveEffectStore,
            "consume_dynamic_bullet",
            new=traced_consume,
        ):
            runtime.run(duration=duration)

        moris = simulate(
            moris_squad,
            config={"duration": duration, "rng_mode": "expected"},
            verbose=True,
        )
        moris_activations = [
            float(row.t)
            for row in moris.log.buff_events
            if row.name == "캄 스나이핑" and row.kind == "activate"
        ]

        self.assertEqual(len(activations), len(moris_activations))
        for actual, expected in zip(activations, moris_activations):
            self.assertAlmostEqual(actual, expected, places=9)
        self.assertGreaterEqual(len(activations), 2)
        self.assertGreaterEqual(len(removals), len(activations) - 1)

        for activation, removal in zip(activations, removals):
            next_shot = next(shot for shot in shots if shot > activation + 1e-9)
            self.assertAlmostEqual(removal, next_shot, places=9)
            self.assertGreater(removal, activation)

        self.assertAlmostEqual(activations[0], 3.8, places=9)
        self.assertAlmostEqual(removals[0], 5.2, places=9)

    def test_public_frontier_only_loses_the_d_delivery_blocker(self):
        seen = set()
        matching_shapes = []
        blockers = []
        certified = 0
        for team, entry in snapshot.SQUADS.items():
            if team.startswith("지그_"):
                continue
            members = tuple(entry["members"])
            if members in seen:
                continue
            seen.add(members)
            compiled = compile_moris_squad(spec.build_squad(list(members)))
            rows = static_score_blockers(compiled)
            blockers.extend(rows)
            certified += not rows
            for effect in compiled.effects:
                if (
                    effect.parameters.get("duration_bullets") is not None
                    and any(rule.event_key == "full_charge_hit" for rule in effect.triggers)
                    and is_direct_damage_buff_runtime_supported(effect)
                ):
                    matching_shapes.append(
                        (
                            compiled.members[effect.actor].name,
                            effect.name,
                            effect.stat,
                            effect.parameters.get("duration_bullets"),
                        )
                    )

        self.assertEqual(len(seen), 23)
        self.assertEqual(certified, 0)
        self.assertNotIn(self.BLOCKER, blockers)
        self.assertEqual(
            matching_shapes,
            [("D : 킬러 와이프", "캄 스나이핑", "pierce_enabled", 1)],
        )


if __name__ == "__main__":
    unittest.main()
