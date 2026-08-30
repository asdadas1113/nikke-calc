from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.synergy import PairSynergyProbe, measure_pair_probes


class FakeEvaluator:
    def __init__(self, scores):
        self.scores = {tuple(team): float(score) for team, score in scores.items()}
        self.calls = []

    def evaluate(self, members, **kwargs):
        team = tuple(members)
        self.calls.append((team, kwargs))
        return SimpleNamespace(score=self.scores[team])


class PairSynergyProbeTests(unittest.TestCase):
    def test_four_point_interaction_uses_fixed_slots(self):
        probe = PairSynergyProbe(
            pair=("X", "Y"),
            reference=("A", "B", "C", "D", "E"),
            positions=(0, 1),
        )
        evaluator = FakeEvaluator(
            {
                ("A", "B", "C", "D", "E"): 100,
                ("X", "B", "C", "D", "E"): 120,
                ("A", "Y", "C", "D", "E"): 130,
                ("X", "Y", "C", "D", "E"): 170,
            }
        )

        rows = measure_pair_probes(evaluator, (probe,))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].probe.replaced, ("A", "B"))
        self.assertEqual(rows[0].interaction_delta, 20)
        self.assertEqual(
            [team for team, _ in evaluator.calls],
            [
                ("A", "B", "C", "D", "E"),
                ("X", "B", "C", "D", "E"),
                ("A", "Y", "C", "D", "E"),
                ("X", "Y", "C", "D", "E"),
            ],
        )

    def test_pair_placement_order_is_explicit(self):
        probe = PairSynergyProbe(
            pair=("Y", "X"),
            reference=("A", "B", "C", "D", "E"),
            positions=(3, 1),
        )
        self.assertEqual(probe.first_only(), ("A", "B", "C", "Y", "E"))
        self.assertEqual(probe.second_only(), ("A", "X", "C", "D", "E"))
        self.assertEqual(probe.paired(), ("A", "X", "C", "Y", "E"))

    def test_invalid_probe_is_rejected(self):
        with self.assertRaises(ValueError):
            PairSynergyProbe(
                pair=("A", "X"),
                reference=("A", "B", "C", "D", "E"),
                positions=(0, 1),
            )
        with self.assertRaises(ValueError):
            PairSynergyProbe(
                pair=("X", "Y"),
                reference=("A", "B", "C", "D", "E"),
                positions=(2, 2),
            )

    def test_hard_legality_failure_is_not_silently_skipped(self):
        probe = PairSynergyProbe(
            pair=("X", "Y"),
            reference=("A", "B", "C", "D", "E"),
            positions=(0, 1),
        )
        evaluator = FakeEvaluator({})

        with self.assertRaisesRegex(ValueError, "illegal team"):
            measure_pair_probes(
                evaluator,
                (probe,),
                legal=lambda team: "Y" not in team,
            )
        self.assertEqual(evaluator.calls, [])


if __name__ == "__main__":
    unittest.main()
