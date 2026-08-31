from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_same_budget_auto_worker.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_same_budget_auto_worker", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class DiscoverySummaryTests(unittest.TestCase):
    def test_summary_exposes_simulation_free_work_separately(self):
        ordinary = SimpleNamespace(
            candidates=(1, 2, 3),
            expanded_states=11,
            rejected_illegal=2,
        )
        allocation = SimpleNamespace(
            allocations=(1,),
            candidates=(1, 2),
            expanded_states=17,
            rejected_illegal=3,
        )
        bundle = SimpleNamespace(ordinary=ordinary, allocation=allocation)
        discovery = SimpleNamespace(
            bundles=(("first", bundle),),
            source_views=("first",),
            skipped_views=(),
            ordinary_teams=(("A", "B"),),
            protected_channels=((('A', 'B'),),),
            protected_teams=(("A", "B"),),
        )
        result = SimpleNamespace(
            discovery=discovery,
            search=SimpleNamespace(candidate_evaluation_order=(("A", "B"),)),
        )

        summary = RUNNER._discovery_summary(result)
        self.assertEqual(summary["cheap_work"]["ordinary_expanded_states"], 11)
        self.assertEqual(summary["cheap_work"]["allocation_expanded_states"], 17)
        self.assertEqual(summary["cheap_work"]["total_expanded_states"], 28)
        self.assertEqual(summary["cheap_work"]["total_rejected_illegal"], 5)
        self.assertEqual(summary["views"][0]["name"], "first")
        self.assertNotIn("score", summary["cheap_work"])


if __name__ == "__main__":
    unittest.main()
