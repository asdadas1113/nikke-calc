from __future__ import annotations

import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).with_name("benchmark_optimizer_account_scale.py")
spec = importlib.util.spec_from_file_location("benchmark_optimizer_account_scale", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class AccountScaleBenchmarkParserTests(unittest.TestCase):
    def test_team_parser_preserves_order(self):
        self.assertEqual(module.team(["A", "B", "C"], "x"), ("A", "B", "C"))

    def test_team_parser_rejects_duplicate_members(self):
        with self.assertRaisesRegex(ValueError, "duplicate members"):
            module.team(["A", "A"], "x")

    def test_names_parser_requires_explicit_list(self):
        with self.assertRaisesRegex(ValueError, "explicit string list"):
            module.names("all", "x")

    def test_allocation_rows_handles_missing_allocation(self):
        self.assertEqual(module.allocation_rows(None), [])


if __name__ == "__main__":
    unittest.main()
