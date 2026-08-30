from __future__ import annotations

import copy
import unittest

from optimizer.account import AccountSyncAdapter, ProvenanceStatus


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


def char_entry(*, skill3: int = 7) -> dict:
    return {
        "breakthrough": 3,
        "core_enhancement": 1,
        "affinity": 30,
        "skill_levels": {"1": 8, "2": 9, "3": skill3},
        "equipment": {
            "머리": {"level": 5},
            "몸통": {"tier": "없음"},
            "팔": {"level": 3},
            "다리": {"tier": "T9"},
        },
        "equip_skills": {key: ([] if key in ("max_ammo_pct", "charge_speed_pct") else 0.0)
                         for key in EQUIP_KEYS},
        "collection_stage": "SR10",
    }


def payload() -> dict:
    return {
        "_meta": {
            "name": "fixture",
            "openid": "must-not-survive-normalization",
            "area": 83,
            "fetched_at": "2026-08-30T20:00:00+09:00",
            "source": "profile-sync fixture",
        },
        "_account": {
            "synchro_level": 410,
            "console": {
                "common_level": 100,
                "class_level": {"화력형": 90, "방어형": 91, "지원형": 92},
                "company_level": {
                    "엘리시온": 80,
                    "미실리스": 81,
                    "테트라": 82,
                    "필그림": 83,
                    "어브노말": 84,
                },
            },
            "console_warnings": [],
            "cubes": {"렐릭 베어 큐브": 10},
        },
        "chars": {
            "리타": char_entry(),
            "크라운": char_entry(skill3=10),
        },
    }


class AccountSnapshotTests(unittest.TestCase):
    def test_normalizes_sync_payload_without_exposing_openid(self):
        snapshot = AccountSyncAdapter.normalize(payload())

        self.assertEqual(snapshot.roster, ("리타", "크라운"))
        self.assertFalse(snapshot.blocking_unknowns)
        self.assertNotIn("openid", snapshot.profile_payload["_meta"])
        self.assertTrue(snapshot.snapshot_id.startswith("acct-"))
        fixed = [p for p in snapshot.provenance if p.path == "policy.level"]
        self.assertEqual(fixed[0].status, ProvenanceStatus.DEFAULTED)

    def test_snapshot_identity_tracks_build_not_fetch_timestamp(self):
        first = payload()
        second = copy.deepcopy(first)
        second["_meta"]["fetched_at"] = "2026-08-31T01:00:00+09:00"
        same = AccountSyncAdapter.normalize(first).snapshot_id
        self.assertEqual(same, AccountSyncAdapter.normalize(second).snapshot_id)

        second["chars"]["리타"]["skill_levels"]["3"] = 1
        self.assertNotEqual(same, AccountSyncAdapter.normalize(second).snapshot_id)

    def test_missing_build_field_is_unknown_and_blocks_default_policy(self):
        data = payload()
        del data["chars"]["리타"]["skill_levels"]["3"]
        snapshot = AccountSyncAdapter.normalize(data)

        self.assertIn(
            "chars.리타.skill_levels.3",
            {item.path for item in snapshot.blocking_unknowns},
        )
        with self.assertRaisesRegex(ValueError, "refusing Moris fixed-build fallback"):
            snapshot.to_growth_profile()

    def test_explicit_moris_default_policy_preserves_unknown_provenance(self):
        data = payload()
        del data["chars"]["리타"]["equipment"]["머리"]
        snapshot = AccountSyncAdapter.normalize(data, unknown_policy="moris-default")

        self.assertTrue(snapshot.blocking_unknowns)
        self.assertIn("explicit Moris-default fallback allowed", " ".join(snapshot.notes()))
        self.assertIsNotNone(snapshot.to_growth_profile())

    def test_console_preservation_is_not_reported_as_fresh_observation(self):
        data = payload()
        data["_account"]["console_warnings"] = ["current outpost response incomplete"]
        snapshot = AccountSyncAdapter.normalize(data)
        row = next(item for item in snapshot.provenance if item.path == "_account.console")
        self.assertEqual(row.status, ProvenanceStatus.PRESERVED)

    def test_missing_console_blocks_instead_of_inheriting_fixed_console(self):
        data = payload()
        data["_account"]["console"] = None
        snapshot = AccountSyncAdapter.normalize(data)
        self.assertIn("_account.console", {item.path for item in snapshot.blocking_unknowns})

    def test_sync_level_mode_requires_synchro_level(self):
        data = payload()
        data["_account"]["synchro_level"] = None
        snapshot = AccountSyncAdapter.normalize(data, level_mode="sync")
        self.assertIn(
            "_account.synchro_level",
            {item.path for item in snapshot.blocking_unknowns},
        )


if __name__ == "__main__":
    unittest.main()
