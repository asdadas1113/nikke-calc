from __future__ import annotations

import copy
import unittest

from optimizer.overload import (
    OverloadKnowledge,
    derive_overload_piece_evidence,
)


EQUIP_KEYS = (
    "atk_pct",
    "element_bonus",
    "max_ammo_pct",
    "crit_rate",
    "crit_dmg",
    "charge_speed_pct",
    "charge_dmg_pct",
    "accuracy_pct",
    "def_pct",
)
PARTS = ("head", "torso", "arm", "leg")


def entry() -> dict:
    return {
        "equip_skills": {
            key: ([] if key in ("max_ammo_pct", "charge_speed_pct") else 0.0)
            for key in EQUIP_KEYS
        }
    }


def profile() -> dict:
    return {"chars": {"A": entry(), "B": entry()}}


def detail(code: int) -> dict:
    out = {"name_code": code}
    for part in PARTS:
        for slot in (1, 2, 3):
            out[f"{part}_equip_option{slot}_id"] = 0
    return out


def raw() -> dict:
    return {"details": [detail(101), detail(102)]}


class OverloadEvidenceTests(unittest.TestCase):
    def test_complete_zero_is_the_only_proven_zero_path(self):
        evidence = derive_overload_piece_evidence(
            profile(), raw(), name_by_code={101: "A", 102: "B"}
        )

        self.assertEqual(evidence["A"].knowledge, OverloadKnowledge.ZERO)
        self.assertEqual(evidence["A"].piece_count, 0)
        self.assertTrue(evidence["A"].proven_zero)
        self.assertFalse(evidence["A"].protected_from_cold_filter)

    def test_complete_raw_slots_count_overload_parts_not_option_lines(self):
        data = raw()
        data["details"][0]["head_equip_option1_id"] = 9001
        data["details"][0]["head_equip_option2_id"] = 9002
        data["details"][0]["leg_equip_option3_id"] = 9003

        evidence = derive_overload_piece_evidence(
            profile(), data, name_by_code={101: "A", 102: "B"}
        )["A"]

        self.assertEqual(evidence.knowledge, OverloadKnowledge.PRESENT)
        self.assertEqual(evidence.piece_count, 2)
        self.assertTrue(evidence.protected_from_cold_filter)

    def test_incomplete_raw_with_profile_presence_protects_but_does_not_guess_count(self):
        prof = profile()
        prof["chars"]["A"]["equip_skills"]["atk_pct"] = 11.81
        data = raw()
        del data["details"][0]["head_equip_option1_id"]

        evidence = derive_overload_piece_evidence(
            prof, data, name_by_code={101: "A", 102: "B"}
        )["A"]

        self.assertEqual(evidence.knowledge, OverloadKnowledge.PRESENT)
        self.assertIsNone(evidence.piece_count)
        self.assertTrue(evidence.protected_from_cold_filter)

    def test_incomplete_raw_and_zero_profile_is_unknown_not_zero(self):
        data = raw()
        del data["details"][0]["head_equip_option1_id"]

        evidence = derive_overload_piece_evidence(
            profile(), data, name_by_code={101: "A", 102: "B"}
        )["A"]

        self.assertEqual(evidence.knowledge, OverloadKnowledge.UNKNOWN)
        self.assertIsNone(evidence.piece_count)
        self.assertTrue(evidence.protected_from_cold_filter)

    def test_missing_name_mapping_is_unknown_unless_profile_proves_presence(self):
        prof = profile()
        first = derive_overload_piece_evidence(
            prof, raw(), name_by_code={102: "B"}
        )["A"]
        self.assertEqual(first.knowledge, OverloadKnowledge.UNKNOWN)

        prof2 = copy.deepcopy(prof)
        prof2["chars"]["A"]["equip_skills"]["crit_rate"] = 5.0
        second = derive_overload_piece_evidence(
            prof2, raw(), name_by_code={102: "B"}
        )["A"]
        self.assertEqual(second.knowledge, OverloadKnowledge.PRESENT)
        self.assertIsNone(second.piece_count)

    def test_profile_raw_zero_conflict_is_unknown(self):
        prof = profile()
        prof["chars"]["A"]["equip_skills"]["element_bonus"] = 20.0

        evidence = derive_overload_piece_evidence(
            prof, raw(), name_by_code={101: "A", 102: "B"}
        )["A"]

        self.assertEqual(evidence.knowledge, OverloadKnowledge.UNKNOWN)
        self.assertTrue(evidence.protected_from_cold_filter)

    def test_string_zero_option_ids_remain_zero(self):
        data = raw()
        for key in list(data["details"][0]):
            if key.endswith("_id"):
                data["details"][0][key] = "0"

        evidence = derive_overload_piece_evidence(
            profile(), data, name_by_code={101: "A", 102: "B"}
        )["A"]
        self.assertEqual(evidence.knowledge, OverloadKnowledge.ZERO)


if __name__ == "__main__":
    unittest.main()
