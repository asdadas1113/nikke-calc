from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from optimizer import CoreSeed, ExactCompSeed


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_same_budget_auto_enikk_worker.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_same_budget_auto_enikk_worker", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def prepared():
    hypotheses = SimpleNamespace(
        seeds=SimpleNamespace(
            exact_seeds=(ExactCompSeed(("A", "B"), source="exact"),),
            core_seeds=(CoreSeed(("C", "D"), source="core"),),
        ),
        skipped_before_adaptation=(),
        references=SimpleNamespace(compositions=()),
    )
    discovery = SimpleNamespace(unfulfilled_sources=())
    return SimpleNamespace(
        hypotheses=hypotheses,
        references=(("A", "B"),),
        common_simulate_calls=2,
        discovery=discovery,
    )


def meta_payload():
    return {
        "completed_through": "2026-08-31",
        "policy": {"completed_seasons": 8, "max_peak_usage": 0.01},
        "schedule": {"periods": [], "complete": True, "source": "fixture"},
        "coverage_contract": {
            "servers": ["GLOBAL"],
            "rank_start": 1,
            "rank_end": 1,
            "team_count": 5,
            "team_size": 5,
            "source": "fixture-contract",
        },
        "snapshots": [],
        "restoration_batch_size": 1,
        "cold_exploration_limit": 0,
        "protected_names": [],
    }


class SameBudgetAutoEnikkWorkerTests(unittest.TestCase):
    def test_external_seed_mode_meta_only_does_not_touch_pure(self):
        plan = {}
        RUNNER._append_external_seeds(plan, prepared(), "meta")
        self.assertNotIn("pure_seeds", plan)
        self.assertEqual(plan["meta_seeds"]["exact"][0]["members"], ["A", "B"])
        self.assertEqual(plan["meta_seeds"]["core"][0]["members"], ["C", "D"])

    def test_external_seed_mode_both_appends_to_existing_rows(self):
        plan = {
            "pure_seeds": {"exact": [{"members": ["X", "Y"], "source": "old"}], "core": []},
            "meta_seeds": {"exact": [], "core": []},
        }
        RUNNER._append_external_seeds(plan, prepared(), "both")
        self.assertEqual(len(plan["pure_seeds"]["exact"]), 2)
        self.assertEqual(len(plan["meta_seeds"]["exact"]), 1)
        self.assertEqual(len(plan["meta_seeds"]["core"]), 1)

    def test_external_seed_mode_must_be_explicit_valid_value(self):
        with self.assertRaisesRegex(ValueError, "off/both/pure/meta"):
            RUNNER._append_external_seeds({}, prepared(), "auto")

    def test_change_events_are_resolved_to_explicit_owned_epochs(self):
        payload = meta_payload()
        payload["change_events"] = [
            {
                "character": "A",
                "effective_on": "2026-05-01",
                "effect": "reset",
                "kind": "favorite-item",
                "source": "patch-source",
            }
        ]
        resolved, counts = RUNNER._resolved_meta_payload(payload, ("A", "B"))

        self.assertNotIn("change_events", resolved)
        self.assertEqual(resolved["epochs"]["A"]["knowledge"], "known")
        self.assertEqual(resolved["epochs"]["A"]["valid_from"], "2026-05-01")
        self.assertEqual(resolved["epochs"]["B"]["knowledge"], "unknown")
        self.assertEqual(counts, {"known": 1, "unknown": 1})

    def test_first_availability_and_later_change_share_registry_mode(self):
        payload = meta_payload()
        payload["first_availability"] = [
            {
                "character": "A",
                "knowledge": "known",
                "available_from": "2025-01-01",
                "mechanism": "special-recruit",
                "source": "official-release",
            },
            {
                "character": "B",
                "knowledge": "unknown",
                "mechanism": "unknown",
                "source": "registry-missing",
            },
        ]
        payload["change_events"] = [
            {
                "character": "A",
                "effective_on": "2026-05-01",
                "effect": "reset",
                "kind": "favorite-item",
                "source": "official-favorite",
            }
        ]
        resolved, counts = RUNNER._resolved_meta_payload(payload, ("A", "B"))

        self.assertNotIn("first_availability", resolved)
        self.assertNotIn("change_events", resolved)
        self.assertEqual(resolved["epochs"]["A"]["knowledge"], "known")
        self.assertEqual(resolved["epochs"]["A"]["valid_from"], "2026-05-01")
        self.assertEqual(resolved["epochs"]["B"]["knowledge"], "unknown")
        self.assertEqual(counts, {"known": 1, "unknown": 1})
        self.assertEqual(
            RUNNER._epoch_input_mode(payload),
            "first_availability+change_events",
        )

    def test_first_availability_alone_is_normalized(self):
        payload = meta_payload()
        payload["first_availability"] = [
            {
                "character": "A",
                "knowledge": "known",
                "available_from": "2026-07-02",
                "mechanism": "special-recruit",
                "source": "official-release",
            }
        ]
        resolved, counts = RUNNER._resolved_meta_payload(payload, ("A", "B"))
        self.assertEqual(resolved["epochs"]["A"]["valid_from"], "2026-07-02")
        self.assertEqual(resolved["epochs"]["B"]["knowledge"], "unknown")
        self.assertEqual(counts, {"known": 1, "unknown": 1})
        self.assertEqual(RUNNER._epoch_input_mode(payload), "first_availability")

    def test_explicit_epochs_and_registry_evidence_are_rejected_together(self):
        payload = meta_payload()
        payload["epochs"] = {}
        payload["change_events"] = []
        with self.assertRaisesRegex(ValueError, "registry evidence"):
            RUNNER._resolved_meta_payload(payload, ("A",))

        payload = meta_payload()
        payload["epochs"] = {}
        payload["first_availability"] = []
        with self.assertRaisesRegex(ValueError, "registry evidence"):
            RUNNER._resolved_meta_payload(payload, ("A",))

    def test_no_epoch_mode_becomes_unknown_for_every_owned_character(self):
        resolved, counts = RUNNER._resolved_meta_payload(meta_payload(), ("A", "B"))
        self.assertEqual(counts, {"unknown": 2})
        self.assertEqual(
            {row["knowledge"] for row in resolved["epochs"].values()},
            {"unknown"},
        )
        self.assertEqual(RUNNER._epoch_input_mode(meta_payload()), "none")


if __name__ == "__main__":
    unittest.main()
