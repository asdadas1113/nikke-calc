from __future__ import annotations

from collections import Counter
import json
import unittest

from fast_engine.research.public_ranking_probe import run_public_probe


class PublicRankingCoverageProbe(unittest.TestCase):
    def test_surface_current_standardized_corpus(self):
        report = run_public_probe(top_n=10, top_k=20)
        rows = report["rows"]
        certified = [row for row in rows if row["certified_fast_score"] is not None]
        blocked = [row for row in rows if row["certified_fast_score"] is None]
        exact_blockers = Counter(
            blocker
            for row in blocked
            for blocker in row["blockers"]
        )
        exact_unsupported = Counter(
            item
            for row in rows
            for item in row["unsupported"]
        )
        moris_top10 = sorted(rows, key=lambda row: row["moris_score"], reverse=True)[:10]
        compact = {
            "team_count": report["team_count"],
            "certified_team_count": report["certified_team_count"],
            "coverage_gap_count": report["coverage_gap_count"],
            "moris_sim_seconds": report["moris_sim_seconds"],
            "fast_score_seconds": report["fast_score_seconds_certified_or_attempted"],
            "coverage": report["certified_top_n_in_top_k"],
            "clean_ranking": report["clean_ranking"],
            "clean_relative_error": report["clean_relative_error"],
            "blocker_family_counts": report["blocker_family_counts"],
            "unsupported_family_counts": report["unsupported_family_counts"],
            "top_exact_blockers": exact_blockers.most_common(30),
            "top_exact_unsupported": exact_unsupported.most_common(30),
            "certified_rows": [
                {
                    "source": row["source_name"],
                    "members": row["members"],
                    "moris": row["moris_score"],
                    "fast": row["certified_fast_score"],
                    "relative_error": row["relative_error"],
                }
                for row in sorted(certified, key=lambda row: row["moris_score"], reverse=True)
            ],
            "moris_top10": [
                {
                    "source": row["source_name"],
                    "members": row["members"],
                    "moris": row["moris_score"],
                    "fast": row["certified_fast_score"],
                    "relative_error": row["relative_error"],
                    "blockers": row["blockers"],
                    "unsupported": row["unsupported"],
                }
                for row in moris_top10
            ],
        }
        self.fail(
            "INTENTIONAL_PUBLIC_RANKING_RERUN="
            + json.dumps(compact, ensure_ascii=False, sort_keys=True)
        )


if __name__ == "__main__":
    unittest.main()
