from __future__ import annotations

import unittest

from optimizer.seeds import CoreSeed, ExactCompSeed, select_seed_candidates


def legal_pair(team):
    return len(team) == 2 and len(set(team)) == 2 and "X" not in team


class SeedCandidateTests(unittest.TestCase):
    def test_exact_seed_is_protected_without_score_or_candidate_universe(self):
        result = select_seed_candidates(
            (),
            exact_seeds=(ExactCompSeed(("A", "B"), source="ranking"),),
            roster=("A", "B", "C"),
            legal=legal_pair,
        )

        self.assertEqual(
            tuple((item.members, item.seed_kind, item.seed_source) for item in result.candidates),
            ((('A', 'B'), 'exact', 'ranking'),),
        )
        self.assertEqual(result.unfulfilled_exact, ())

    def test_exact_seed_fails_open_when_unowned_or_hard_illegal(self):
        unowned = ExactCompSeed(("A", "C"))
        illegal = ExactCompSeed(("A", "X"))
        result = select_seed_candidates(
            (),
            exact_seeds=(unowned, illegal),
            roster=("A", "B", "X"),
            legal=legal_pair,
        )

        self.assertEqual(result.candidates, ())
        self.assertEqual(result.unfulfilled_exact, (unowned, illegal))

    def test_core_seed_selects_only_from_caller_candidate_universe(self):
        result = select_seed_candidates(
            (("A", "C"), ("A", "B"), ("B", "A"), ("A", "B")),
            core_seeds=(CoreSeed(("A", "B"), source="known-core"),),
            roster=("A", "B", "C"),
            legal=legal_pair,
            max_per_core=2,
        )

        self.assertEqual(
            tuple(item.members for item in result.candidates),
            (("A", "B"), ("B", "A")),
        )
        self.assertTrue(all(item.seed_kind == "core" for item in result.candidates))
        self.assertEqual(result.unfulfilled_cores, ())

    def test_core_seed_does_not_invent_missing_combinations(self):
        seed = CoreSeed(("A", "B"))
        result = select_seed_candidates(
            (("A", "C"), ("B", "C")),
            core_seeds=(seed,),
            roster=("A", "B", "C"),
            legal=legal_pair,
        )

        self.assertEqual(result.candidates, ())
        self.assertEqual(result.unfulfilled_cores, (seed,))

    def test_duplicate_nominations_do_not_duplicate_evaluations(self):
        result = select_seed_candidates(
            (("A", "B"),),
            exact_seeds=(ExactCompSeed(("A", "B"), source="exact"),),
            core_seeds=(CoreSeed(("A", "B"), source="core"),),
            roster=("A", "B"),
            legal=legal_pair,
        )

        self.assertEqual(tuple(item.members for item in result.candidates), (("A", "B"),))

    def test_rejects_invalid_core_and_negative_limits(self):
        with self.assertRaises(ValueError):
            CoreSeed(("A",))
        with self.assertRaises(ValueError):
            select_seed_candidates((), max_per_core=-1)


if __name__ == "__main__":
    unittest.main()
