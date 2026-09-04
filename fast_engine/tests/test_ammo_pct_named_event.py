from __future__ import annotations

import unittest

from context import snapshot, spec
from fast_engine.engine.burst import BurstPolicy, BurstSignal
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
import fast_engine.engine.score as score
from fast_engine.tests.test_damage_dynamic_ammo_charge import _ammo_effect, _named_consumer, _squad


class TovePctInstantNamedEventABTests(unittest.TestCase):
    def test_synthetic_pct_provider_emits_named_event_and_is_score_safe(self):
        refill = _ammo_effect(stat="ammo_charge_pct", value=25.0)
        followup = _named_consumer()
        squad = _squad((refill, followup))
        blockers = score.static_score_blockers(squad)
        self.assertNotIn("cadence:synthetic-reload:refill:ammo_charge_pct", blockers)
        self.assertNotIn("normal_delivery:synthetic-reload:named followup:atk_pct", blockers)
        runtime = BurstRuntime(squad, BurstPolicy(duration=5.0, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=5.0))
        runtime.dispatcher.attach_ammo_charge_sink(lambda stat, targets, value, now: True)
        runtime.dispatcher.dispatch(BurstSignal(1.0, "burst_cast", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(refill.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(followup.effect_id, 0), 1)
        self.assertAlmostEqual(runtime.dispatcher.effects.sum_stat(0, "atk_pct", now=1.01), 10.0, places=9)

    def test_flat_named_provider_remains_fail_closed_and_does_not_emit(self):
        refill = _ammo_effect(stat="ammo_charge_flat", value=1.0)
        followup = _named_consumer()
        squad = _squad((refill, followup))
        self.assertIn("cadence:synthetic-reload:refill:ammo_charge_flat", score.static_score_blockers(squad))
        runtime = BurstRuntime(squad, BurstPolicy(duration=5.0, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=5.0))
        runtime.dispatcher.attach_ammo_charge_sink(lambda stat, targets, value, now: True)
        runtime.dispatcher.dispatch(BurstSignal(1.0, "burst_cast", 0, 0))
        self.assertEqual(runtime.dispatcher._activation_counts.get(refill.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(followup.effect_id, 0), 0)

    def test_real_tove_consumer_source_is_certified_and_runtime_event_fires(self):
        squad = compile_moris_squad(spec.build_squad(list(snapshot.SQUADS["레이드_소다"]["members"])))
        tove = next(i for i, member in enumerate(squad.members) if member.name == "토브")
        provider = next(e for e in squad.members[tove].effects if e.name == "급조 탄환")
        followup = next(e for e in squad.members[tove].effects if e.name == "임시 개조 2")
        self.assertTrue(score._direct_damage_buff_score_supported(squad, followup))
        blockers = score.static_score_blockers(squad)
        self.assertNotIn("normal_delivery:토브:임시 개조 2:crit_dmg", blockers)
        self.assertNotIn("skill_state_delivery:토브:임시 개조 2:crit_dmg", blockers)
        self.assertIn("cadence:토브:임시 개조:max_ammo_flat", blockers)
        runtime = BurstRuntime(squad, BurstPolicy(duration=5.0, first_burst_time=30.0), EnemyStaticProfile(defense=0.0, duration=5.0))
        runtime.dispatcher.attach_ammo_charge_sink(lambda stat, targets, value, now: True)
        for n in range(10):
            runtime.dispatcher.dispatch(BurstSignal(0.1 * n, "hit_count", tove, tove))
        self.assertEqual(runtime.dispatcher._activation_counts.get(provider.effect_id, 0), 1)
        self.assertEqual(runtime.dispatcher._activation_counts.get(followup.effect_id, 0), 1)
        for actor in range(len(squad.members)):
            self.assertAlmostEqual(runtime.dispatcher.effects.sum_stat(actor, "crit_dmg", now=0.91), float(followup.value or 0.0), places=9)


if __name__ == "__main__":
    unittest.main()
