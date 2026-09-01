from __future__ import annotations

import unittest
from pathlib import Path

from context.spec import build_squad
from fast_engine.engine import EnemyStaticProfile, EventKind, EventScheduler, compile_moris_squad
from fast_engine.tools.damage_semantics_inventory import inventory


class EnemyProfileTests(unittest.TestCase):
    def test_core_rate_is_aggregated_not_timeline_script(self):
        enemy = EnemyStaticProfile(core_uptime=0.6, core_hit_rate_when_open=0.75)
        self.assertAlmostEqual(enemy.effective_core_rate, 0.45)

    def test_invalid_core_rate_fails_fast(self):
        with self.assertRaises(ValueError):
            EnemyStaticProfile(core_uptime=1.1)


class SchedulerTests(unittest.TestCase):
    def test_scheduler_is_continuous_time_and_stable(self):
        q = EventScheduler()
        q.schedule(2.431, EventKind.STATE_EXPIRE, actor=1, payload="a")
        q.schedule(0.125, EventKind.BURST_READY, actor=0)
        q.schedule(2.431, EventKind.TRIGGER_BOUNDARY, actor=2, payload="b")
        events = [q.pop(), q.pop(), q.pop()]
        self.assertEqual([e.time for e in events], [0.125, 2.431, 2.431])
        self.assertEqual([e.payload for e in events[1:]], ["a", "b"])

    def test_equal_time_events_follow_moris_frame_phases(self):
        q = EventScheduler()
        # Deliberately enqueue in the opposite order. Moris runs BuffManager.tick
        # (expiry then every:N) before burst controller and weapon actors.
        q.schedule(20.0, EventKind.WEAPON_BOUNDARY, payload="weapon")
        q.schedule(20.0, EventKind.FULL_BURST_START, payload="burst")
        q.schedule(20.0, EventKind.PERIODIC_TICK, payload="periodic")
        q.schedule(20.0, EventKind.STATE_EXPIRE, payload="expiry")
        self.assertEqual(
            [q.pop().payload for _ in range(4)],
            ["expiry", "periodic", "burst", "weapon"],
        )

    def test_equal_time_same_phase_remains_stable(self):
        q = EventScheduler()
        q.schedule(3.0, EventKind.BURST_READY, payload="first")
        q.schedule(3.0, EventKind.BURST_ACTIVATE, payload="second")
        self.assertEqual([q.pop().payload, q.pop().payload], ["first", "second"])

    def test_cannot_schedule_into_past(self):
        q = EventScheduler()
        q.schedule(1.0, EventKind.CUSTOM)
        q.pop()
        with self.assertRaises(ValueError):
            q.schedule(0.9, EventKind.CUSTOM)


class MorisCompatibilityTests(unittest.TestCase):
    def test_real_moris_squad_compiles_without_rebuilding_growth_logic(self):
        names = ["리타", "크라운", "홍련", "앨리스", "나가"]
        squad = build_squad(names)
        compiled = compile_moris_squad(squad)
        self.assertEqual(compiled.names, tuple(names))
        self.assertEqual(len(compiled.members), 5)
        self.assertTrue(all(c.base_atk > 0 for c in compiled.members))
        self.assertTrue(all(c.effects for c in compiled.members))
        self.assertEqual(compiled.members[1].burst_stage, "2")


class DamageSemanticsInventoryTests(unittest.TestCase):
    def test_current_moris_effect_inventory_has_no_unclassified_rows(self):
        root = Path(__file__).resolve().parents[2]
        inv = inventory(root)
        self.assertEqual(inv["effects"], 1799)
        self.assertEqual(inv["unknown_stats"], {})
        self.assertEqual(sum(inv["counts"].values()), inv["effects"])


if __name__ == "__main__":
    unittest.main()
