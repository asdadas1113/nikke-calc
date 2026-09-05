from __future__ import annotations

import unittest

from fast_engine.engine.scheduler import EventKind, EventScheduler
from fast_engine.engine.shot_blocks import ShotBlock, ShotBlockCursor


class SparseSameTimestampActorTransactionTests(unittest.TestCase):
    @staticmethod
    def _cursor(actor: int, time: float = 1.0) -> ShotBlockCursor:
        return ShotBlockCursor((ShotBlock(actor, time, 1, 1.0),))

    def test_phase30_events_sort_by_actor_before_insertion_order(self):
        scheduler = EventScheduler()
        scheduler.schedule(1.0, EventKind.TRIGGER_BOUNDARY, actor=3, payload="late")
        scheduler.schedule(1.0, EventKind.WEAPON_BOUNDARY, actor=1, payload="early")
        scheduler.schedule(1.0, EventKind.TRIGGER_BOUNDARY, actor=1, payload="same-actor")

        first = scheduler.pop()
        second = scheduler.pop()
        third = scheduler.pop()

        self.assertEqual((first.actor, first.payload), (1, "early"))
        self.assertEqual((second.actor, second.payload), (1, "same-actor"))
        self.assertEqual((third.actor, third.payload), (3, "late"))

    def test_exact_timestamp_static_shots_wait_for_current_actor_prefix(self):
        scheduler = EventScheduler()
        scheduler.schedule(1.0, EventKind.TRIGGER_BOUNDARY, actor=2)
        scheduler.schedule(1.0, EventKind.TRIGGER_BOUNDARY, actor=0)
        cursors = tuple(self._cursor(actor) for actor in range(3))

        event = scheduler.pop()
        self.assertEqual(event.actor, 0)
        self.assertEqual(cursors[0].consume_until(1.0, inclusive=True), 1)
        self.assertEqual(cursors[1].consume_until(1.0, inclusive=True), 0)
        self.assertEqual(cursors[2].consume_until(1.0, inclusive=True), 0)

        self.assertEqual(scheduler.peek_time(), 1.0)
        event = scheduler.pop()
        self.assertEqual(event.actor, 2)
        self.assertEqual(cursors[1].consume_until(1.0, inclusive=True), 1)
        self.assertEqual(cursors[2].consume_until(1.0, inclusive=True), 1)

    def test_end_of_timestamp_releases_later_actor_shots(self):
        scheduler = EventScheduler()
        scheduler.schedule(1.0, EventKind.TRIGGER_BOUNDARY, actor=0)
        scheduler.schedule(2.0, EventKind.TRIGGER_BOUNDARY, actor=0)
        later = self._cursor(1)

        event = scheduler.pop()
        self.assertEqual(event.actor, 0)
        self.assertEqual(later.consume_until(1.0, inclusive=True), 0)

        self.assertEqual(scheduler.peek_time(), 2.0)
        self.assertEqual(later.consume_until(1.0, inclusive=True), 1)


if __name__ == "__main__":
    unittest.main()
