from __future__ import annotations

import unittest

from optimizer.refinement import generate_one_swap_neighbors


class OneSwapRefinementTests(unittest.TestCase):
    def test_default_preserves_replaced_slot_and_order(self):
        rows = generate_one_swap_neighbors(
            (("A", "B", "C"),),
            ("A", "B", "C", "X", "Y"),
            positions=(1,),
        )

        self.assertEqual(
            [row.members for row in rows],
            [("A", "X", "C"), ("A", "Y", "C")],
        )
        self.assertEqual(rows[0].outgoing, "B")
        self.assertEqual(rows[0].incoming, "X")
        self.assertEqual(rows[0].position, 1)

    def test_seen_identity_preserves_order_semantics(self):
        rows = generate_one_swap_neighbors(
            (("A", "B", "C"),),
            ("A", "B", "C", "X"),
            positions=(1,),
            seen=(("X", "A", "C"),),
        )

        # Same member set in a different placement is not the same evaluated key.
        self.assertEqual([row.members for row in rows], [("A", "X", "C")])

    def test_fixture_can_supply_explicit_placement_resolver(self):
        order = {name: index for index, name in enumerate(("A", "B", "C", "X"))}

        rows = generate_one_swap_neighbors(
            (("B", "C", "X"),),
            ("A", "B", "C", "X"),
            positions=(2,),
            placement_resolver=lambda team: tuple(sorted(team, key=order.__getitem__)),
        )

        self.assertEqual([row.members for row in rows], [("A", "B", "C")])
        self.assertEqual(rows[0].outgoing, "X")
        self.assertEqual(rows[0].incoming, "A")

    def test_hard_legality_and_seen_are_applied_before_budget(self):
        rows = generate_one_swap_neighbors(
            (("A", "B", "C"),),
            ("A", "B", "C", "X", "Y", "Z"),
            positions=(0,),
            seen=(("X", "B", "C"),),
            legal=lambda team: "Y" not in team,
            max_new=1,
        )

        self.assertEqual([row.members for row in rows], [("Z", "B", "C")])

    def test_duplicate_neighbors_from_multiple_seeds_are_emitted_once(self):
        rows = generate_one_swap_neighbors(
            (("A", "B", "C"), ("A", "B", "D")),
            ("A", "B", "C", "D"),
        )

        keys = [row.members for row in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_invalid_budget_or_resolver_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_one_swap_neighbors(
                (("A", "B"),),
                ("A", "B", "X"),
                max_new=-1,
            )

        with self.assertRaisesRegex(ValueError, "must not change team membership"):
            generate_one_swap_neighbors(
                (("A", "B"),),
                ("A", "B", "X"),
                positions=(0,),
                placement_resolver=lambda team: ("A", "B"),
            )


if __name__ == "__main__":
    unittest.main()
