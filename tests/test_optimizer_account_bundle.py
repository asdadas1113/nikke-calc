from __future__ import annotations

import copy
import unittest

from optimizer.account import ProvenanceStatus
from optimizer.account_bundle import normalize_account_bundle


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


def char_entry() -> dict:
    return {
        "breakthrough": 3,
        "core_enhancement": 0,
        "affinity": 10,
        "skill_levels": {"1": 7, "2": 7, "3": 7},
        "equipment": {
            "머리": {"tier": "없음"},
            "몸통": {"tier": "없음"},
            "팔": {"tier": "없음"},
            "다리": {"tier": "없음"},
        },
        "equip_skills": {
            key: ([] if key in ("max_ammo_pct", "charge_speed_pct") else 0.0)
            for key in EQUIP_KEYS
        },
        "collection_stage": "없음",
    }


def profile() -> dict:
    return {
        "_meta": {
            "name": "bundle-fixture",
            "openid": "private-id-not-part-of-snapshot-output",
            "area": 83,
            "fetched_at": "2026-08-30T23:00:00+09:00",
            "roster": 2,
        },
        "_account": {
            "synchro_level": 400,
            "console": {
                "common_level": 1,
                "class_level": {"화력형": 1, "방어형": 1, "지원형": 1},
                "company_level": {
                    "엘리시온": 1,
                    "미실리스": 1,
                    "테트라": 1,
                    "필그림": 1,
                    "어브노말": 1,
                },
            },
            "console_warnings": [],
            "cubes": {},
        },
        "chars": {"A": char_entry(), "B": char_entry()},
    }


def detail(code: int) -> dict:
    row = {
        "name_code": code,
        "favorite_item_tid": 0,
        "attractive_lv": 10,
    }
    for part in PARTS:
        for index in (1, 2, 3):
            row[f"{part}_equip_option{index}_id"] = 0
    return row


def raw() -> dict:
    return {
        "openid": "private-id-not-part-of-snapshot-output",
        "area": 83,
        "characters": [{"name_code": 101}, {"name_code": 102}],
        "details": [detail(101), detail(102)],
        "state_effects": [],
    }


class AuditedAccountSnapshotTests(unittest.TestCase):
    def test_clean_bundle_has_no_blocking_unknowns(self):
        snapshot = normalize_account_bundle(profile(), raw())

        self.assertFalse(snapshot.blocking_unknowns)
        self.assertTrue(snapshot.snapshot_id.startswith("acct-audit-"))
        console = next(item for item in snapshot.provenance if item.path == "_account.console")
        self.assertEqual(console.status, ProvenanceStatus.UNCERTAIN)

    def test_unmapped_equipped_overload_type_blocks(self):
        data = raw()
        data["details"][0]["head_equip_option1_id"] = 9001
        data["state_effects"] = [
            {
                "id": 9001,
                "function_details": [
                    {"function_type": "FutureUnknownStat", "function_value": 1234}
                ],
            }
        ]
        snapshot = normalize_account_bundle(profile(), data)

        self.assertIn(
            "chars.*.equip_skills.unmapped_function_type",
            {item.path for item in snapshot.blocking_unknowns},
        )
        with self.assertRaisesRegex(ValueError, "audited account snapshot"):
            snapshot.to_growth_profile()

    def test_missing_option_dictionary_entry_blocks(self):
        data = raw()
        data["details"][0]["head_equip_option1_id"] = 9002
        snapshot = normalize_account_bundle(profile(), data)
        self.assertIn(
            "chars.*.equip_skills.raw_dictionary",
            {item.path for item in snapshot.blocking_unknowns},
        )

    def test_off_table_known_option_is_uncertain_not_unknown(self):
        data = raw()
        data["details"][0]["head_equip_option1_id"] = 9003
        data["state_effects"] = [
            {
                "id": 9003,
                "function_details": [
                    {"function_type": "StatAtk", "function_value": 987654}
                ],
            }
        ]
        snapshot = normalize_account_bundle(profile(), data)

        row = next(
            item
            for item in snapshot.provenance
            if item.path == "chars.*.equip_skills.off_table_value"
        )
        self.assertEqual(row.status, ProvenanceStatus.UNCERTAIN)
        self.assertFalse(snapshot.blocking_unknowns)

    def test_roster_count_or_name_code_mismatch_blocks(self):
        data = raw()
        data["details"].pop()
        snapshot = normalize_account_bundle(profile(), data)
        self.assertIn(
            "roster.raw_sidecar",
            {item.path for item in snapshot.blocking_unknowns},
        )

    def test_nonempty_collection_count_mismatch_blocks(self):
        data = raw()
        data["details"][0]["favorite_item_tid"] = 123456
        snapshot = normalize_account_bundle(profile(), data)
        self.assertIn(
            "chars.*.collection_stage.raw_mapping",
            {item.path for item in snapshot.blocking_unknowns},
        )

    def test_non_sim_unsynced_flag_does_not_change_audited_identity(self):
        first = profile()
        second = copy.deepcopy(first)
        second["chars"]["A"]["_unsynced"] = True

        self.assertEqual(
            normalize_account_bundle(first, raw()).snapshot_id,
            normalize_account_bundle(second, raw()).snapshot_id,
        )

    def test_audit_provenance_changes_snapshot_identity(self):
        clean = normalize_account_bundle(profile(), raw()).snapshot_id
        data = raw()
        data["details"][0]["head_equip_option1_id"] = 9004
        data["state_effects"] = [
            {
                "id": 9004,
                "function_details": [
                    {"function_type": "FutureUnknownStat", "function_value": 100}
                ],
            }
        ]
        audited = normalize_account_bundle(
            profile(), data, unknown_policy="moris-default"
        ).snapshot_id
        self.assertNotEqual(clean, audited)

    def test_raw_affinity_zero_is_recorded_as_policy_default(self):
        data = raw()
        data["details"][0]["attractive_lv"] = 0
        snapshot = normalize_account_bundle(profile(), data)
        row = next(item for item in snapshot.provenance if item.path == "policy.affinity_floor")
        self.assertEqual(row.status, ProvenanceStatus.DEFAULTED)

    def test_explicit_moris_default_keeps_audit_unknown_visible(self):
        data = raw()
        data["details"][0]["head_equip_option1_id"] = 9005
        data["state_effects"] = [
            {
                "id": 9005,
                "function_details": [
                    {"function_type": "FutureUnknownStat", "function_value": 100}
                ],
            }
        ]
        snapshot = normalize_account_bundle(
            profile(), data, unknown_policy="moris-default"
        )
        self.assertTrue(snapshot.blocking_unknowns)
        self.assertIn("explicit Moris-default fallback allowed", " ".join(snapshot.notes()))


if __name__ == "__main__":
    unittest.main()
