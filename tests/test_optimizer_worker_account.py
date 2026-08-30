from __future__ import annotations

import json
import unittest
from pathlib import Path

from optimizer.overload import OverloadKnowledge, derive_overload_piece_evidence
from optimizer.worker_account import build_worker_account_bundle


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


def _detail(name: str, *, option_id: int = 0):
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
    if option_id:
        row["head_equip_tier"] = 10
        row["head_equip_option1_id"] = option_id
    return row


def _payload():
    names = ("네온", "아니스")
    return {
        "openid": "must-not-survive",
        "areas": [
            {
                "area": 83,
                "characters": [
                    {"name_code": CODE_BY_NAME[name], "grade": 0, "core": 0, "lv": 1}
                    for name in names
                ],
                "details": [_detail("네온"), _detail("아니스")],
                "stateEffects": [],
                "outpost": {
                    "synchro_level": 350,
                    "recycle_room_researches": _console_rows(),
                },
            }
        ],
    }


class WorkerAccountBundleTests(unittest.TestCase):
    def test_bundle_exposes_snapshot_profile_and_identifier_free_raw_sidecar(self):
        bundle = build_worker_account_bundle(_payload())

        self.assertEqual(set(bundle.roster), {"네온", "아니스"})
        self.assertFalse(bundle.blocking_unknowns)
        self.assertNotIn("openid", bundle.raw_sidecar)
        self.assertNotIn("openid", json.dumps(bundle.profile_payload, ensure_ascii=False))
        self.assertNotIn("must-not-survive", json.dumps(bundle.raw_sidecar, ensure_ascii=False))
        self.assertNotIn("must-not-survive", bundle.snapshot.snapshot_id)

    def test_bundle_raw_sidecar_can_prove_zero_overload_pieces(self):
        bundle = build_worker_account_bundle(_payload())
        overload = derive_overload_piece_evidence(
            bundle.profile_payload,
            bundle.raw_sidecar,
        )

        self.assertEqual(overload["네온"].knowledge, OverloadKnowledge.ZERO)
        self.assertEqual(overload["네온"].piece_count, 0)
        self.assertEqual(overload["아니스"].knowledge, OverloadKnowledge.ZERO)


if __name__ == "__main__":
    unittest.main()
