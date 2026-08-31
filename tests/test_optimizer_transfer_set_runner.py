from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "tests" / "benchmark_optimizer_transfer_set.py"
SPEC = importlib.util.spec_from_file_location("benchmark_optimizer_transfer_set", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class TransferSetRunnerTests(unittest.TestCase):
    def test_zip_workers_are_materialized_with_anonymous_local_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "workers.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("person-b.json", json.dumps({"characters": []}))
                archive.writestr("person-a.json", json.dumps({"characters": []}))
                archive.writestr("notes.txt", "ignored")

            with RUNNER.materialize_workers(archive_path) as workers:
                self.assertEqual([row.source_label for row in workers], ["person-a.json", "person-b.json"])
                self.assertEqual([row.path.name for row in workers], ["worker-001.json", "worker-002.json"])
                self.assertTrue(all(row.path.exists() for row in workers))

    def test_unsafe_zip_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "workers.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.json", "{}")
            with self.assertRaisesRegex(ValueError, "unsafe ZIP member"):
                with RUNNER.materialize_workers(archive_path):
                    pass

    def test_summary_counts_wins_and_cold_flow(self):
        rows = [
            {
                "sample": "sample_001",
                "status": "ok",
                "damage_delta": 10.0,
                "relative_damage_delta": 0.10,
                "initial_cold_count": 3,
                "restored_count": 1,
                "explored_cold_count": 1,
                "still_deferred_cold_count": 1,
            },
            {
                "sample": "sample_002",
                "status": "ok",
                "damage_delta": 0.0,
                "relative_damage_delta": 0.0,
                "initial_cold_count": 2,
                "restored_count": 0,
                "explored_cold_count": 1,
                "still_deferred_cold_count": 1,
            },
            {
                "sample": "sample_003",
                "status": "ok",
                "damage_delta": -5.0,
                "relative_damage_delta": -0.05,
                "initial_cold_count": 1,
                "restored_count": 0,
                "explored_cold_count": 0,
                "still_deferred_cold_count": 1,
            },
            {"sample": "sample_004", "status": "error", "error": "fixture"},
        ]
        summary = RUNNER.summarize(rows)
        self.assertEqual(summary["sample_count"], 4)
        self.assertEqual(summary["successful_count"], 3)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["meta_win_count"], 1)
        self.assertEqual(summary["tie_count"], 1)
        self.assertEqual(summary["pure_win_count"], 1)
        self.assertAlmostEqual(summary["mean_relative_damage_delta"], (0.10 + 0.0 - 0.05) / 3)
        self.assertEqual(summary["total_initial_cold"], 6)
        self.assertEqual(summary["total_restored"], 1)
        self.assertEqual(summary["total_explored_cold"], 2)
        self.assertEqual(summary["total_still_deferred_cold"], 3)

    def test_result_row_does_not_copy_snapshot_identity(self):
        result = {
            "snapshot_id": "sensitive-fingerprint",
            "roster_count": 100,
            "pure_search_roster_count": 100,
            "meta_search_roster_count": 80,
            "meta_initial_cold": ["A"],
            "meta_restored": [],
            "meta_explored_cold": [],
            "meta_still_deferred_cold": ["A"],
            "actual_equal_simulate_calls": 50,
            "pure": {
                "final_damage": 100.0,
                "runtime_s": 2.0,
                "stage_calls": {},
                "allocation": [],
            },
            "meta": {
                "final_damage": 110.0,
                "runtime_s": 1.5,
                "stage_calls": {},
                "allocation": [],
            },
            "meta_minus_pure_damage": 10.0,
            "meta_minus_pure_relative": 0.1,
            "false_deferred": None,
            "false_deferred_reason": "unknown",
        }
        row = RUNNER._result_row("sample_001", result)
        self.assertNotIn("snapshot_id", row)
        self.assertEqual(row["sample"], "sample_001")


if __name__ == "__main__":
    unittest.main()
