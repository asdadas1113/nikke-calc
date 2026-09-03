from __future__ import annotations

import unittest

from fast_engine.research.public_ranking_probe import ProbeRow, _dedupe_rows_by_members


class PublicRankingProbeContractTests(unittest.TestCase):
    @staticmethod
    def _row(source_name: str, *, moris_score: float = 100.0) -> ProbeRow:
        return ProbeRow(
            source_name=source_name,
            members=("A", "B", "C", "D", "E"),
            moris_score=moris_score,
            raw_fast_score=99.0,
            certified_fast_score=99.0,
            relative_error=-0.01,
            blockers=(),
            unsupported=(),
            groups=("weapon:AR",),
            moris_seconds=1.0,
            fast_seconds=0.01,
        )

    def test_duplicate_source_cases_collapse_to_one_ranking_candidate(self):
        first = self._row("source-a")
        duplicate = self._row("source-b")

        unique = _dedupe_rows_by_members([first, duplicate])

        self.assertEqual(unique, [first])

    def test_duplicate_membership_with_different_evidence_fails_closed(self):
        first = self._row("source-a")
        divergent = self._row("source-b", moris_score=101.0)

        with self.assertRaisesRegex(AssertionError, "duplicate standardized membership diverged"):
            _dedupe_rows_by_members([first, divergent])


if __name__ == "__main__":
    unittest.main()
