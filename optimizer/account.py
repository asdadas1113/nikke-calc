"""Normalize Moris profile-sync output into an optimizer account snapshot.

The optimizer deliberately consumes the *calculator-facing* sync artifact
(`profiles/<name>.json`) instead of reimplementing blablalink raw API parsing.
`scraper/profile_fetch.py` remains the source of truth for raw account sync.

A snapshot keeps provenance and an explicit unknown-field policy. Missing build
fields are never silently called "observed" and the default policy is to reject
simulation when a missing field would otherwise fall through to Moris' fixed
build defaults.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


_SYNC_CHAR_KEYS = frozenset({
    "breakthrough",
    "core_enhancement",
    "affinity",
    "skill_levels",
    "equipment",
    "equip_skills",
    "collection_stage",
    "favorite_stage",
})
_REQUIRED_CHAR_KEYS = (
    "breakthrough",
    "core_enhancement",
    "affinity",
    "skill_levels",
    "equipment",
    "equip_skills",
    "collection_stage",
)
_SKILL_KEYS = ("1", "2", "3")
_EQUIPMENT_PARTS = ("머리", "몸통", "팔", "다리")
_EQUIP_SKILL_KEYS = (
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
_LEVEL_MODES = ("fixed", "sync")
_UNKNOWN_POLICIES = ("error", "moris-default")
_FAVORITE_CHARS: frozenset[str] | None = None


class ProvenanceStatus(str, Enum):
    OBSERVED = "observed"
    PRESERVED = "preserved"
    DEFAULTED = "defaulted"
    UNKNOWN = "unknown"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class FieldProvenance:
    path: str
    status: ProvenanceStatus
    source: str
    affects_simulation: bool
    note: str = ""


@dataclass(frozen=True)
class AccountSnapshot:
    """Normalized private account build state used by every optimizer stage."""

    name: str
    level_mode: str
    unknown_policy: str
    profile_payload: Mapping[str, Any]
    provenance: tuple[FieldProvenance, ...]
    snapshot_id: str

    @property
    def roster(self) -> tuple[str, ...]:
        chars = self.profile_payload.get("chars") or {}
        return tuple(chars.keys())

    @property
    def blocking_unknowns(self) -> tuple[FieldProvenance, ...]:
        return tuple(
            item
            for item in self.provenance
            if item.status is ProvenanceStatus.UNKNOWN and item.affects_simulation
        )

    @property
    def defaulted_fields(self) -> tuple[FieldProvenance, ...]:
        return tuple(
            item for item in self.provenance if item.status is ProvenanceStatus.DEFAULTED
        )

    def to_growth_profile(self, *, allow_unowned: bool = False):
        """Build Moris' existing GrowthProfile without touching calculator internals."""
        if self.unknown_policy == "error" and self.blocking_unknowns:
            paths = ", ".join(item.path for item in self.blocking_unknowns[:12])
            extra = len(self.blocking_unknowns) - 12
            if extra > 0:
                paths += f", ... +{extra}"
            raise ValueError(
                "account snapshot has unknown simulation fields; refusing Moris fixed-build "
                f"fallback: {paths}"
            )
        from context.spec import GrowthProfile

        return GrowthProfile(
            copy.deepcopy(dict(self.profile_payload)),
            allow_unowned=allow_unowned,
            level_mode=self.level_mode,
        )

    def notes(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.blocking_unknowns:
            mode = (
                "simulation blocked"
                if self.unknown_policy == "error"
                else "explicit Moris-default fallback allowed"
            )
            out.append(
                f"unknown simulation fields: {len(self.blocking_unknowns)} ({mode})"
            )
        preserved = sum(
            item.status in (ProvenanceStatus.PRESERVED, ProvenanceStatus.UNCERTAIN)
            for item in self.provenance
            if item.affects_simulation
        )
        if preserved:
            out.append(f"simulation fields with preserved/uncertain provenance: {preserved}")
        if self.defaulted_fields:
            out.append(f"explicit policy defaults: {len(self.defaulted_fields)}")
        return tuple(out)


def _favorite_characters() -> frozenset[str]:
    """Characters for which a missing favorite_stage would silently mean stage 3."""
    global _FAVORITE_CHARS
    if _FAVORITE_CHARS is None:
        from context import spec as char_spec

        root = Path(char_spec.__file__).resolve().parent.parent
        parsed = json.loads((root / "data" / "parsed_nikke.json").read_text(encoding="utf-8"))
        _FAVORITE_CHARS = frozenset(
            name
            for name, row in parsed.items()
            if isinstance(row, Mapping) and row.get("favorite_slots")
        )
    return _FAVORITE_CHARS


class AccountSyncAdapter:
    """Normalize `profile_fetch.py` output into a stable AccountSnapshot."""

    @classmethod
    def normalize(
        cls,
        payload: Mapping[str, Any],
        *,
        level_mode: str = "fixed",
        unknown_policy: str = "error",
    ) -> AccountSnapshot:
        if level_mode not in _LEVEL_MODES:
            raise ValueError(f"level_mode must be one of {_LEVEL_MODES}: {level_mode!r}")
        if unknown_policy not in _UNKNOWN_POLICIES:
            raise ValueError(
                f"unknown_policy must be one of {_UNKNOWN_POLICIES}: {unknown_policy!r}"
            )

        raw_chars = payload.get("chars")
        if not isinstance(raw_chars, Mapping) or not raw_chars:
            raise ValueError("account sync payload must contain a non-empty `chars` mapping")

        meta_in = payload.get("_meta") if isinstance(payload.get("_meta"), Mapping) else {}
        account_in = (
            payload.get("_account") if isinstance(payload.get("_account"), Mapping) else {}
        )
        name = str(meta_in.get("name") or "account")
        provenance: list[FieldProvenance] = []
        chars: dict[str, dict[str, Any]] = {}
        favorite_chars = _favorite_characters()

        for char_name in sorted(str(name) for name in raw_chars):
            source_entry = raw_chars[char_name]
            if not isinstance(source_entry, Mapping):
                raise ValueError(f"chars.{char_name} must be an object")
            bad = sorted(
                key
                for key in source_entry
                if not str(key).startswith("_") and key not in _SYNC_CHAR_KEYS
            )
            if bad:
                raise ValueError(
                    f"chars.{char_name} contains fields outside canonical profile-sync growth data: {bad}"
                )
            entry = copy.deepcopy(dict(source_entry))
            chars[char_name] = entry
            cls._record_character_provenance(
                char_name,
                entry,
                provenance,
                requires_favorite_stage=char_name in favorite_chars,
            )

        account: dict[str, Any] = {}
        for key in (
            "synchro_level",
            "console",
            "console_warnings",
            "cubes",
            "_synchro_note",
            "_console_note",
            "_cubes_note",
        ):
            if key in account_in:
                account[key] = copy.deepcopy(account_in[key])

        console = account.get("console")
        console_warnings = account.get("console_warnings") or []
        if console is None:
            provenance.append(
                FieldProvenance(
                    "_account.console",
                    ProvenanceStatus.UNKNOWN,
                    "profile-sync",
                    True,
                    "missing console would otherwise inherit Moris fixed-build console values",
                )
            )
        else:
            provenance.append(
                FieldProvenance(
                    "_account.console",
                    ProvenanceStatus.PRESERVED if console_warnings else ProvenanceStatus.OBSERVED,
                    "profile-sync:outpost",
                    True,
                    "profile_fetch preserves the previous console when current outpost data is incomplete"
                    if console_warnings
                    else "recycle-room levels supplied by profile sync",
                )
            )

        synchro_level = account.get("synchro_level")
        if level_mode == "sync":
            if synchro_level is None:
                provenance.append(
                    FieldProvenance(
                        "_account.synchro_level",
                        ProvenanceStatus.UNKNOWN,
                        "profile-sync",
                        True,
                        "sync level mode requires synchro_level",
                    )
                )
            else:
                provenance.append(
                    FieldProvenance(
                        "_account.synchro_level",
                        ProvenanceStatus.UNCERTAIN,
                        "profile-sync:outpost-or-preserved",
                        True,
                        "legacy profile format does not prove whether this value was freshly observed or preserved",
                    )
                )
        else:
            provenance.append(
                FieldProvenance(
                    "policy.level",
                    ProvenanceStatus.DEFAULTED,
                    "optimizer:solo-raid-fixed-level",
                    True,
                    "Moris DEFAULT_CHAR level 400 is intentionally retained for Solo Raid",
                )
            )

        cubes = account.get("cubes")
        provenance.append(
            FieldProvenance(
                "_account.cubes",
                ProvenanceStatus.OBSERVED if cubes else ProvenanceStatus.UNKNOWN,
                "profile-sync:equipped-cube-lower-bound",
                False,
                "sync only observes equipped cubes; cube choice remains a case/config axis",
            )
        )
        provenance.append(
            FieldProvenance(
                "policy.cube",
                ProvenanceStatus.DEFAULTED,
                "Moris character/default or caller case setting",
                False,
                "not claimed as account-observed build data",
            )
        )

        meta = {
            "name": name,
            "area": meta_in.get("area"),
            "fetched_at": meta_in.get("fetched_at"),
            "source": meta_in.get("source") or "profile-sync",
            "roster": len(chars),
        }
        normalized = {"_meta": meta, "_account": account, "chars": chars}
        identity_payload = {
            "schema": 1,
            "level_mode": level_mode,
            "unknown_policy": unknown_policy,
            "account": account,
            "chars": chars,
        }
        encoded = json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        snapshot_id = "acct-" + hashlib.sha256(encoded).hexdigest()[:24]
        return AccountSnapshot(
            name=name,
            level_mode=level_mode,
            unknown_policy=unknown_policy,
            profile_payload=normalized,
            provenance=tuple(provenance),
            snapshot_id=snapshot_id,
        )

    @staticmethod
    def _record_character_provenance(
        char_name: str,
        entry: Mapping[str, Any],
        provenance: list[FieldProvenance],
        *,
        requires_favorite_stage: bool,
    ) -> None:
        base = f"chars.{char_name}"
        for key in _REQUIRED_CHAR_KEYS:
            if key not in entry:
                provenance.append(
                    FieldProvenance(
                        f"{base}.{key}",
                        ProvenanceStatus.UNKNOWN,
                        "profile-sync",
                        True,
                        "missing field must not silently inherit Moris fixed-build values",
                    )
                )
            else:
                provenance.append(
                    FieldProvenance(
                        f"{base}.{key}",
                        ProvenanceStatus.OBSERVED,
                        "profile-sync:character-details",
                        True,
                        "profile-sync transformed calculator-facing value",
                    )
                )

        skills = entry.get("skill_levels") if isinstance(entry.get("skill_levels"), Mapping) else {}
        for key in _SKILL_KEYS:
            if key not in skills:
                provenance.append(
                    FieldProvenance(
                        f"{base}.skill_levels.{key}",
                        ProvenanceStatus.UNKNOWN,
                        "profile-sync",
                        True,
                        "missing skill level would otherwise inherit fixed-build level 10",
                    )
                )

        equipment = entry.get("equipment") if isinstance(entry.get("equipment"), Mapping) else {}
        for part in _EQUIPMENT_PARTS:
            row = equipment.get(part)
            if (
                not isinstance(row, Mapping)
                or ("level" not in row and "tier" not in row)
            ):
                provenance.append(
                    FieldProvenance(
                        f"{base}.equipment.{part}",
                        ProvenanceStatus.UNKNOWN,
                        "profile-sync",
                        True,
                        "missing/empty equipment part would otherwise inherit fixed-build equipment",
                    )
                )

        equip_skills = (
            entry.get("equip_skills") if isinstance(entry.get("equip_skills"), Mapping) else {}
        )
        for key in _EQUIP_SKILL_KEYS:
            if key not in equip_skills:
                provenance.append(
                    FieldProvenance(
                        f"{base}.equip_skills.{key}",
                        ProvenanceStatus.UNKNOWN,
                        "profile-sync",
                        True,
                        "missing overload field would otherwise inherit fixed-build overload values",
                    )
                )

        if requires_favorite_stage:
            if "favorite_stage" not in entry:
                provenance.append(
                    FieldProvenance(
                        f"{base}.favorite_stage",
                        ProvenanceStatus.UNKNOWN,
                        "profile-sync",
                        True,
                        "favorite character would otherwise inherit fixed-build favorite stage 3",
                    )
                )
            else:
                provenance.append(
                    FieldProvenance(
                        f"{base}.favorite_stage",
                        ProvenanceStatus.OBSERVED,
                        "profile-sync:favorite-item",
                        True,
                        "favorite stage selects the Moris skill revision",
                    )
                )


def normalize_account_sync(
    payload: Mapping[str, Any],
    *,
    level_mode: str = "fixed",
    unknown_policy: str = "error",
) -> AccountSnapshot:
    return AccountSyncAdapter.normalize(
        payload,
        level_mode=level_mode,
        unknown_policy=unknown_policy,
    )
