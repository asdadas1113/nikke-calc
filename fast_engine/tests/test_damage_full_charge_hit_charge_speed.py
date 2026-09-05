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
from fast_engine.engine.dynamic_weapon import MultiSignalChargeCadenceRuntime
from fast_engine.engine.effects import ActiveEffectStore
from fast_engine.engine.score import static_score_blockers


class FullChargeHitChargeSpeedTests(unittest.TestCase):
    BLOCKER = 'cadence:신데렐라:무결한 유리 2:charge_speed_pct'

    def _fixture(self):
        team = next(
            name for name, entry in snapshot.SQUADS.items()
            if not name.startswith('지그_') and '신데렐라' in entry['members']
        )
        moris = spec.build_squad(list(snapshot.SQUADS[team]['members']))
        compiled = compile_moris_squad(moris)
        actor = next(i for i, member in enumerate(compiled.members) if member.name == '신데렐라')
        effect = next(
            effect for effect in compiled.members[actor].effects
            if effect.name == '무결한 유리 2'
        )
        return team, moris, compiled, actor, effect

    def test_real_shape_removes_only_its_cadence_blocker(self):
        _team, _moris, compiled, _actor, effect = self._fixture()
        helper = TriggerDispatcher._full_charge_hit_permanent_self_charge_speed_shape_supported
        self.assertTrue(helper(effect))
        blockers = set(static_score_blockers(compiled))
        self.assertNotIn(self.BLOCKER, blockers)
        self.assertTrue(blockers)

        seen = set()
        matches = []
        cadence = 0
        certified = 0
        for team, entry in snapshot.SQUADS.items():
            if team.startswith('지그_'):
                continue
            members = tuple(entry['members'])
            if members in seen:
                continue
            seen.add(members)
            squad = compile_moris_squad(spec.build_squad(list(members)))
            team_blockers = static_score_blockers(squad)
            cadence += sum(row.startswith('cadence:') for row in team_blockers)
            certified += not team_blockers
            for candidate in squad.effects:
                if helper(candidate):
                    matches.append(
                        (team, squad.members[candidate.actor].name, candidate.name, candidate.stat)
                    )
        self.assertEqual(len(seen), 23)
        self.assertEqual(certified, 2)
        self.assertEqual(cadence, 59)
        self.assertEqual(len(matches), 2)
        self.assertEqual(
            {(row[1], row[2], row[3]) for row in matches},
            {('신데렐라', '무결한 유리 2', 'charge_speed_pct')},
        )

    def test_fast_full_charge_activation_sequence_matches_moris(self):
        _team, moris_squad, compiled, actor, effect = self._fixture()
        duration = 20.0
        policy = compile_burst_policy(moris_squad, compiled, {'duration': duration})
        fast_activations = []
        fast_shots = []
        original_activate = ActiveEffectStore.activate_group
        original_boundary = MultiSignalChargeCadenceRuntime.handle_boundary

        def traced_activate(store, candidate, targets, now, scheduler):
            if candidate.effect_id == effect.effect_id:
                fast_activations.append(float(now))
            return original_activate(store, candidate, targets, now, scheduler)

        def traced_boundary(runtime, event):
            row = original_boundary(runtime, event)
            if row is not None and row.actor == actor and any(
                signal.event_key == 'full_charge_hit' for signal in row.signals
            ):
                fast_shots.append(float(event.time))
            return row

        with patch.object(ActiveEffectStore, 'activate_group', new=traced_activate), patch.object(
            MultiSignalChargeCadenceRuntime, 'handle_boundary', new=traced_boundary
        ):
            BurstRuntime(compiled, policy).run(duration=duration)

        moris = simulate(
            moris_squad,
            config={'duration': duration, 'rng_mode': 'expected'},
            verbose=True,
        )
        moris_times = [
            row.t for row in moris.log.buff_events
            if row.name == '무결한 유리 2' and row.kind == 'activate'
        ]
        self.assertEqual(fast_activations, fast_shots)
        self.assertEqual(len(fast_activations), len(moris_times))
        for actual, expected in zip(fast_activations, moris_times):
            self.assertAlmostEqual(actual, expected, places=9)
        self.assertAlmostEqual(fast_activations[0], 1.0, places=9)
        self.assertAlmostEqual(
            fast_activations[1] - fast_activations[0], 1.0 / 3.0, places=9
        )

    def test_neighboring_weapon_hit_shapes_remain_fail_closed(self):
        _team, _moris, _compiled, _actor, effect = self._fixture()
        helper = TriggerDispatcher._full_charge_hit_permanent_self_charge_speed_shape_supported
        self.assertFalse(helper(replace(effect, duration=5.0)))
        self.assertFalse(helper(replace(effect, max_stack=2.0)))
        self.assertFalse(helper(replace(effect, value=-1.0)))

        brady_entry = next(
            entry for entry in snapshot.SQUADS.values()
            if '브래디' in entry['members']
        )
        brady = compile_moris_squad(spec.build_squad(list(brady_entry['members'])))
        self.assertFalse(any(
            helper(candidate)
            for candidate in brady.effects
            if brady.members[candidate.actor].name == '브래디'
        ))


if __name__ == '__main__':
    unittest.main()
