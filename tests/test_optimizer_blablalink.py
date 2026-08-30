from __future__ import annotations

import json
import unittest
from pathlib import Path

from optimizer.blablalink import (
    normalize_blablalink_worker_payload,
    select_blablalink_area,
)


ROOT = Path(__file__).resolve().parents[1]
NAME_CODES = json.loads((ROOT / "data" / "name_codes.json").read_text(encoding="utf-8"))
CODE_BY_NAME = {name: int(code) for code, name in NAME_CODES.items()}


def _console_rows():
    return [
        {"tid": 1001, "lv": 180},
        {"tid": 1101, "lv": 100},
        {"tid": 1102, "lv": 100},
        {"tid": 1103, "lv": 100},
        {"tid": 1201, "lv": 100},
        {"tid": 1202, "lv": 100},
        {"tid": 1203, "lv": 100},
        {"tid": 1204, "lv": 100},
        {"tid": 1205, "lv": 100},
    ]


def _detail(name: str):
    row = {
        "name_code": CODE_BY_NAME[name],
        "attractive_lv": 10,
        "skill1_lv": 4,
        "skill2_lv": 5,
        "ulti_skill_lv": 6,
        "favorite_item_tid": 0,
        "favorite_item_lv": 0,
        "harmony_cube_tid": 0,
        "harmony_cube_lv": 0,
    }
    for part in ("head", "torso", "arm", "leg"):
        row[f"{part}_equip_tier"] = 0
        row[f"{part}_equip_lv"] = 0
        for slot in (1, 2, 3):
            row[f"{part}_equip_option{slot}_id"] = 0
    return row


def _area(area: int, names=("네온", "아니스", "라피")):
    return {
        "area": area,
        "characters": [
            {"name_code": CODE_BY_NAME[name], "grade": 0, "core": 0, "lv": 1}
            for name in names
        ],
        "details": [_detail(name) for name in names],
        "stateEffects": [],
        "outpost": {
            "synchro_level": 350,
            "recycle_room_researches": _console_rows(),
        },
    }


class BlablaLinkWorkerAdapterTests(unittest.TestCase):
    def test_normalizes_worker_payload_without_retaining_openid(self):
        payload = {
            "openid": "synthetic-identifier-must-not-survive",
            "areas": [_area(83)],
        }
        snapshot = normalize_blablalink_worker_payload(payload)

        self.assertEqual(set(snapshot.roster), {"네온", "아니스", "라피"})
        self.assertFalse(snapshot.blocking_unknowns)
        encoded = json.dumps(snapshot.profile_payload, ensure_ascii=False)
        self.assertNotIn("synthetic-identifier-must-not-survive", encoded)
        self.assertNotIn("openid", encoded)
        self.assertNotIn("synthetic-identifier-must-not-survive", snapshot.snapshot_id)

    def test_selects_largest_area_unless_preferred_area_is_given(self):
        small = _area(83, ("네온",))
        large = _area(81, ("네온", "아니스", "라피"))
        payload = {"areas": [small, large]}

        self.assertEqual(select_blablalink_area(payload)["area"], 81)
        self.assertEqual(select_blablalink_area(payload, preferred_area=83)["area"], 83)

    def test_unmatched_owned_character_blocks_strict_snapshot(self):
        area = _area(83, ("네온",))
        unknown_code = 999999999
        area["characters"].append({"name_code": unknown_code, "grade": 0, "core": 0, "lv": 1})
        unknown = _detail("네온")
        unknown["name_code"] = unknown_code
        area["details"].append(unknown)

        snapshot = normalize_blablalink_worker_payload({"areas": [area]})
        paths = {item.path for item in snapshot.blocking_unknowns}
        self.assertIn("roster.raw_sidecar", paths)
        with self.assertRaises(ValueError):
            snapshot.to_growth_profile()

    def test_unknown_equipped_overload_function_type_blocks(self):
        area = _area(83, ("네온",))
        area["details"][0]["head_equip_option1_id"] = 999001
        area["stateEffects"] = [
            {
                "id": 999001,
                "function_details": [
                    {"function_type": "SyntheticUnknownStat", "function_value": 1234}
                ],
            }
        ]

        snapshot = normalize_blablalink_worker_payload({"areas": [area]})
        paths = {item.path for item in snapshot.blocking_unknowns}
        self.assertIn("chars.*.equip_skills.unmapped_function_type", paths)

    def test_missing_outpost_console_is_not_hidden_by_fixed_build_default(self):
        area = _area(83, ("네온",))
        area["outpost"] = None

        snapshot = normalize_blablalink_worker_payload({"areas": [area]})
        paths = {item.path for item in snapshot.blocking_unknowns}
        self.assertIn("_account.console", paths)


if __name__ == "__main__":
    unittest.main()
