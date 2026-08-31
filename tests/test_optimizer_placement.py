from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.placement import (
    diverse_grouped_permutation_placements,
    static_burst_priority_group_key,
)


class FakeBurstInspector:
    def inspect(self, team):
        # A and B compete in burst stage 3; C is a unique stage-1 member.
        return SimpleNamespace(
            eligible_by_stage={
                "1": tuple(name for name in team if name == "C"),
                "2": (),
                "3": tuple(name for name in team if name in {"A", "B"}),
            }
        )


class PlacementOrderingTests(unittest.TestCase):
    def test_diverse_order_preserves_every_permutation_once(self):
        members = ("A", "B", "C", "D")
        rows = diverse_grouped_permutation_placements(members)

        self.assertEqual(len(rows), 24)
        self.assertEqual(len(set(rows)), 24)
        self.assertEqual(rows[0], members)
        self.assertEqual({frozenset(row) for row in rows}, {frozenset(members)})

    def test_group_channels_are_rank_round_robin(self):
        members = ("A", "B", "C")
        key = lambda team: tuple(name for name in team if name in {"A", "B"})
        rows = diverse_grouped_permutation_placements(members, group_key=key)
        keys = [key(row) for row in rows]

        # Two structural groups exist: A-before-B and B-before-A. Their first
        # representatives must both appear before either group receives rank 2.
        self.assertEqual(keys[:2], [("A", "B"), ("B", "A")])
        self.assertEqual(keys[2:4], [("A", "B"), ("B", "A")])

    def test_maximin_prefers_slot_diversity_inside_one_group(self):
        members = ("A", "B", "C", "D")
        rows = diverse_grouped_permutation_placements(members)

        # With one group, row 1 is stable canonical. The next row should maximize
        # Hamming distance and therefore move every member to a different slot.
        self.assertEqual(rows[0], members)
        self.assertEqual(sum(a != b for a, b in zip(rows[0], rows[1])), 4)

    def test_unhashable_group_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "hashable"):
            diverse_grouped_permutation_placements(
                ("A", "B", "C"),
                group_key=lambda team: list(team),
            )

    def test_static_burst_key_uses_inspector_candidate_order(self):
        key = static_burst_priority_group_key(FakeBurstInspector())
        self.assertIsNotNone(key)
        assert key is not None

        self.assertNotEqual(
            key(("A", "B", "C")),
            key(("B", "A", "C")),
        )
        # Moving unique-stage C without changing the B3 relative order stays in
        # the same static burst-priority group; slot maximin handles that diversity.
        self.assertEqual(
            key(("A", "C", "B")),
            key(("C", "A", "B")),
        )

    def test_no_inspector_falls_back_to_one_diverse_group(self):
        self.assertIsNone(static_burst_priority_group_key(lambda team: True))
        rows = diverse_grouped_permutation_placements(("A", "B", "C"))
        self.assertEqual(len(rows), 6)


if __name__ == "__main__":
    unittest.main()
