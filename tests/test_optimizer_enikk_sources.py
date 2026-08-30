from __future__ import annotations

import unittest

from optimizer.enikk_sources import collect_enikk_team_dump_compositions
from optimizer.seed_sources import CompositionOrderKnowledge


class EnikkSourceTests(unittest.TestCase):
    def test_dump_maps_resource_ids_and_discards_external_metrics(self):
        result = collect_enikk_team_dump_compositions(
            "1,2,3,4,5=867|8.31|5.84",
            raid=40,
            resource_name_map={
                "1": "A",
                "2": "B",
                "3": "C",
                "4": "D",
                "5": "E",
            },
        )

        self.assertEqual(result.malformed_rows, ())
        self.assertEqual(len(result.evidence), 1)
        row = result.evidence[0]
        self.assertEqual(row.members, ("A", "B", "C", "D", "E"))
        self.assertEqual(row.order_knowledge, CompositionOrderKnowledge.UNKNOWN_ORDER)
        self.assertEqual(row.source, "enikk:S40:teams-row1")
        # No parse-count / max / average field exists on optimizer evidence.
        self.assertFalse(hasattr(row, "uses"))
        self.assertFalse(hasattr(row, "average_damage"))
        self.assertFalse(hasattr(row, "max_damage"))

    def test_unknown_resource_id_remains_incomplete_instead_of_name_guessing(self):
        result = collect_enikk_team_dump_compositions(
            "1,2,3,4,999=5|1.0|0.8",
            raid=40,
            resource_name_map={"1": "A", "2": "B", "3": "C", "4": "D"},
        )
        row = result.evidence[0]
        self.assertFalse(row.mapping_complete)
        self.assertEqual(row.members, ("A", "B", "C", "D"))
        self.assertEqual(row.unmapped_labels, ("999",))

    def test_bad_metrics_are_reported_malformed_not_partially_accepted(self):
        result = collect_enikk_team_dump_compositions(
            "1,2,3,4,5=oops|8.31|5.84 1,2,3,4,5=2|bad|5.84",
            raid=40,
            resource_name_map={str(i): chr(64 + i) for i in range(1, 6)},
        )
        self.assertEqual(result.evidence, ())
        self.assertEqual(len(result.malformed_rows), 2)

    def test_parser_applies_no_hidden_minimum_use_cutoff(self):
        result = collect_enikk_team_dump_compositions(
            "1,2,3,4,5=1|0.1|0.1 5,4,3,2,1=999|99|88",
            raid=40,
            resource_name_map={str(i): chr(64 + i) for i in range(1, 6)},
        )
        self.assertEqual(len(result.evidence), 2)


if __name__ == "__main__":
    unittest.main()
