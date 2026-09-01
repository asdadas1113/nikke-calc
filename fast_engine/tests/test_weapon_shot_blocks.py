from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.shot_blocks import ShotBlock, ShotBlockCursor, compile_static_shot_blocks
from fast_engine.engine.weapon import simulate_static_weapon_cadence


class ShotBlockParityTests(unittest.TestCase):
    NAMES = ["라피", "폴리", "프로덕트 12", "델타", "아니스"]

    @classmethod
    def setUpClass(cls):
        cls.duration = 180.0
        cls.squad = compile_moris_squad(build_squad(cls.NAMES))
        cls.cadence = simulate_static_weapon_cadence(cls.squad, duration=cls.duration)
        cls.blocks = compile_static_shot_blocks(cls.squad, duration=cls.duration)

    def test_block_totals_match_static_cadence_exactly(self):
        for actor, rows in enumerate(self.blocks):
            cadence = self.cadence[actor]
            count = sum(row.count for row in rows)
            self.assertEqual(count, cadence.shots, self.squad.members[actor].name)

            if count:
                self.assertAlmostEqual(rows[0].first_time, cadence.first_shot)
                self.assertAlmostEqual(rows[-1].last_time, cadence.last_shot)

    def test_blocks_are_materially_smaller_than_individual_shots(self):
        total_shots = sum(row.shots for row in self.cadence)
        total_blocks = sum(len(rows) for rows in self.blocks)
        self.assertGreater(total_shots, 1000)
        self.assertLess(total_blocks, total_shots / 10)


class ShotBlockCursorTests(unittest.TestCase):
    def test_equal_time_shot_can_be_deferred_until_after_state_change(self):
        cursor = ShotBlockCursor((ShotBlock(0, 1.0, 4, 1.0),))
        self.assertEqual(cursor.consume_until(3.0, inclusive=False), 2)  # t=1,2
        self.assertEqual(cursor.consume_until(3.0, inclusive=True), 1)   # t=3
        self.assertEqual(cursor.consume_until(10.0, inclusive=True), 1)  # t=4
        self.assertEqual(cursor.consume_until(10.0, inclusive=True), 0)

    def test_zero_interval_block_is_consumed_as_one_batch(self):
        cursor = ShotBlockCursor((ShotBlock(0, 2.0, 5, 0.0),))
        self.assertEqual(cursor.consume_until(2.0, inclusive=False), 0)
        self.assertEqual(cursor.consume_until(2.0, inclusive=True), 5)
        self.assertEqual(cursor.consume_until(3.0, inclusive=True), 0)


if __name__ == "__main__":
    unittest.main()
