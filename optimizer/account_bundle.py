"""Audit a profile-sync profile together with its raw sidecar.

`AccountSyncAdapter` normalizes the calculator-facing `profiles/<name>.json`.
Some sync failures, however, are only visible in `profiles/<name>.raw.json` or in
`profile_fetch.py`'s stdout (for example an overload function type that the
converter does not know).  Production-scale optimizer benchmarks should not call
those silently observed zeroes.

This module therefore keeps the existing profile format untouched and adds a
read-only audit layer over the profile + raw sidecar pair.  It reuses
`scraper.profile_fetch`'s own option mapping/table helpers rather than copying
that knowledge into the optimizer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .account import AccountSnapshot, AccountSyncAdapter, FieldProvenance, ProvenanceStatus


@dataclass(frozen=True)
class AuditedAccountSnapshot:
    """Account snapshot whose identity also covers raw-sync audit provenance."""

    base: AccountSnapshot
    provenance: tuple[FieldProvenance, ...]
    snapshot_id: str

    @property
    def name(self) -> str:
        return self.base.name

    @property
    def level_mode(self) -> str:
        return self.base.level_mode

    @property
    def unknown_policy(self) -> str:
        return self.base.unknown_policy

    @property
    def profile_payload(self) -> Mapping[str, Any]:
        return self.base.profile_payload

    @property
    def roster(self) -> tuple[str, ...]:
        return self.base.roster

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
        if self.unknown_policy == "error" and self.blocking_unknowns:
            paths = ", ".join(item.path for item in self.blocking_unknowns[:12])
            extra = len(self.blocking_unknowns) - 12
            if extra > 0:
                paths += f", ... +{extra}"
            raise ValueError(
                "audited account snapshot has unknown simulation fields; refusing "
                f"Moris fallback: {paths}"
            )
        return self.base.to_growth_profile(allow_unowned=allow_unowned)

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
        uncertain = sum(
            item.status in (ProvenanceStatus.PRESERVED, ProvenanceStatus.UNCERTAIN)
            for item in self.provenance
            if item.affects_simulation
        )
        if uncertain:
            out.append(f"simulation fields with preserved/uncertain provenance: {uncertain}")
        if self.defaulted_fields:
            out.append(f"explicit policy defaults: {len(self.defaulted_fields)}")
        return tuple(out)


def _row(
    path: str,
    status: ProvenanceStatus,
    source: str,
    affects_simulation: bool,
    note: str,
) -> FieldProvenance:
    return FieldProvenance(path, status, source, affects_simulation, note)


def _equipped_option_ids(details: list[Mapping[str, Any]]) -> set[str]:
    from scraper import profile_fetch

    out: set[str] = set()
    for detail in details:
        for api_part, _ in profile_fetch.PARTS:
            for index in (1, 2, 3):
                raw = detail.get(f"{api_part}_equip_option{index}_id", 0)
                if raw:
                    out.add(str(raw))
    return out


def _audit_raw_sidecar(
    profile_payload: Mapping[str, Any],
    raw_payload: Mapping[str, Any],
) -> tuple[FieldProvenance, ...]:
    """Return provenance facts that the calculator-facing profile alone cannot prove."""

    from scraper import profile_fetch

    rows: list[FieldProvenance] = []
    profile_chars = profile_payload.get("chars")
    if not isinstance(profile_chars, Mapping):
        profile_chars = {}

    raw_chars = raw_payload.get("characters")
    details = raw_payload.get("details")
    state_effects = raw_payload.get("state_effects")

    if not isinstance(raw_chars, list) or not isinstance(details, list):
        rows.append(
            _row(
                "roster.raw_sidecar",
                ProvenanceStatus.UNKNOWN,
                "profile-sync:raw-sidecar",
                True,
                "raw sidecar lacks characters/details; owned-roster completeness cannot be audited",
            )
        )
        raw_chars = raw_chars if isinstance(raw_chars, list) else []
        details = details if isinstance(details, list) else []
    else:
        char_codes = [str(row.get("name_code")) for row in raw_chars if row.get("name_code") is not None]
        detail_codes = [str(row.get("name_code")) for row in details if row.get("name_code") is not None]
        complete = (
            len(raw_chars) == len(details) == len(profile_chars)
            and len(char_codes) == len(set(char_codes))
            and len(detail_codes) == len(set(detail_codes))
            and set(char_codes) == set(detail_codes)
        )
        if complete:
            rows.append(
                _row(
                    "roster.raw_sidecar",
                    ProvenanceStatus.OBSERVED,
                    "profile-sync:raw-sidecar",
                    True,
                    f"raw characters/details and normalized roster agree at {len(profile_chars)} entries",
                )
            )
        else:
            rows.append(
                _row(
                    "roster.raw_sidecar",
                    ProvenanceStatus.UNKNOWN,
                    "profile-sync:raw-sidecar",
                    True,
                    "raw characters/details/profile roster counts or name_code sets do not agree",
                )
            )

    meta = profile_payload.get("_meta") if isinstance(profile_payload.get("_meta"), Mapping) else {}
    raw_area = raw_payload.get("area")
    profile_area = meta.get("area")
    raw_openid = raw_payload.get("openid")
    profile_openid = meta.get("openid")
    if raw_area is not None and profile_area is not None and raw_area != profile_area:
        rows.append(
            _row(
                "account.identity",
                ProvenanceStatus.UNKNOWN,
                "profile-sync:raw-sidecar",
                True,
                "profile and raw sidecar area identifiers differ",
            )
        )
    if raw_openid is not None and profile_openid is not None and raw_openid != profile_openid:
        rows.append(
            _row(
                "account.identity",
                ProvenanceStatus.UNKNOWN,
                "profile-sync:raw-sidecar",
                True,
                "profile and raw sidecar account identifiers differ",
            )
        )

    if not isinstance(state_effects, list):
        rows.append(
            _row(
                "chars.*.equip_skills.raw_dictionary",
                ProvenanceStatus.UNKNOWN,
                "profile-sync:raw-sidecar",
                True,
                "raw sidecar lacks state_effects; overload option mapping cannot be audited",
            )
        )
        state_effects = []

    equipped_ids = _equipped_option_ids(details)
    state_by_id = {
        str(row.get("id")): row
        for row in state_effects
        if isinstance(row, Mapping) and row.get("id") is not None
    }
    missing_dictionary = sorted(equipped_ids - set(state_by_id))
    if missing_dictionary:
        rows.append(
            _row(
                "chars.*.equip_skills.raw_dictionary",
                ProvenanceStatus.UNKNOWN,
                "profile-sync:raw-sidecar",
                True,
                f"{len(missing_dictionary)} equipped overload option ids have no state_effect definition",
            )
        )

    unknown_types: set[str] = set()
    for oid in equipped_ids & set(state_by_id):
        effect = state_by_id[oid]
        details_rows = effect.get("function_details") or ()
        if not details_rows:
            rows.append(
                _row(
                    "chars.*.equip_skills.raw_dictionary",
                    ProvenanceStatus.UNKNOWN,
                    "profile-sync:raw-sidecar",
                    True,
                    "an equipped overload option has no function_details",
                )
            )
            continue
        ftype = str(details_rows[0].get("function_type") or "")
        if ftype not in profile_fetch.FUNC_TO_EQUIP:
            unknown_types.add(ftype or "<missing>")
    if unknown_types:
        rows.append(
            _row(
                "chars.*.equip_skills.unmapped_function_type",
                ProvenanceStatus.UNKNOWN,
                "profile-sync:raw-sidecar",
                True,
                "unmapped equipped overload function types: " + ", ".join(sorted(unknown_types)),
            )
        )

    skill_table = profile_fetch._load_equip_skill_table()
    _, _, off_table = profile_fetch._build_option_map(state_effects, skill_table)
    equipped_off_table = [
        (ftype, key, value, sid)
        for ftype, key, value, sid in off_table
        if str(sid) in equipped_ids
    ]
    if equipped_off_table:
        signatures = sorted({f"{ftype}->{key}" for ftype, key, _, _ in equipped_off_table})
        rows.append(
            _row(
                "chars.*.equip_skills.off_table_value",
                ProvenanceStatus.UNCERTAIN,
                "profile-sync:raw-sidecar",
                True,
                "equipped overload values are outside the local level table for: "
                + ", ".join(signatures),
            )
        )

    # A non-zero favorite_item_tid always maps to a non-empty collection stage when
    # profile_fetch knows that item. With a complete roster, a count mismatch is a
    # safe signal that at least one favorite/collection id was converted to NO_ITEM.
    if details and len(details) == len(profile_chars):
        raw_collection_count = sum(bool(row.get("favorite_item_tid", 0)) for row in details)
        profile_collection_count = sum(
            (entry.get("collection_stage") not in (None, profile_fetch.NO_ITEM))
            for entry in profile_chars.values()
            if isinstance(entry, Mapping)
        )
        if raw_collection_count != profile_collection_count:
            rows.append(
                _row(
                    "chars.*.collection_stage.raw_mapping",
                    ProvenanceStatus.UNKNOWN,
                    "profile-sync:raw-sidecar",
                    True,
                    "non-empty raw collection count does not match normalized collection stages",
                )
            )

    if any((row.get("attractive_lv") == 0) for row in details):
        rows.append(
            _row(
                "policy.affinity_floor",
                ProvenanceStatus.DEFAULTED,
                "profile-sync:calculator-domain-floor",
                True,
                "raw affinity 0 is intentionally represented as calculator affinity level 1",
            )
        )

    return tuple(rows)


def _adjust_legacy_provenance(
    base: AccountSnapshot,
) -> tuple[FieldProvenance, ...]:
    """Avoid calling legacy console values freshly observed when the profile cannot prove it."""

    out: list[FieldProvenance] = []
    for item in base.provenance:
        if item.path == "_account.console" and item.status is ProvenanceStatus.OBSERVED:
            out.append(
                replace(
                    item,
                    status=ProvenanceStatus.UNCERTAIN,
                    source="profile-sync:profile-without-freshness-marker",
                    note="profile format does not prove whether console was freshly observed or preserved",
                )
            )
        else:
            out.append(item)
    return tuple(out)


def _snapshot_identity(
    base: AccountSnapshot,
    provenance: tuple[FieldProvenance, ...],
) -> str:
    payload = base.profile_payload
    chars_in = payload.get("chars") if isinstance(payload.get("chars"), Mapping) else {}
    chars = {
        name: {
            key: value
            for key, value in entry.items()
            if not str(key).startswith("_")
        }
        for name, entry in chars_in.items()
        if isinstance(entry, Mapping)
    }
    account_in = payload.get("_account") if isinstance(payload.get("_account"), Mapping) else {}
    account = {"console": account_in.get("console")}
    if base.level_mode == "sync":
        account["synchro_level"] = account_in.get("synchro_level")

    identity = {
        "schema": 1,
        "level_mode": base.level_mode,
        "unknown_policy": base.unknown_policy,
        "account": account,
        "chars": chars,
        "simulation_provenance": [
            {
                "path": item.path,
                "status": item.status.value,
                "source": item.source,
                "note": item.note,
            }
            for item in provenance
            if item.affects_simulation
        ],
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "acct-audit-" + hashlib.sha256(encoded).hexdigest()[:24]


def normalize_account_bundle(
    profile_payload: Mapping[str, Any],
    raw_payload: Mapping[str, Any],
    *,
    level_mode: str = "fixed",
    unknown_policy: str = "error",
) -> AuditedAccountSnapshot:
    """Normalize and raw-audit one profile-sync profile/raw pair.

    The profile is still the only input passed to Moris. The raw sidecar is used
    solely to establish provenance and detect conversion gaps before expensive
    optimizer simulations begin.
    """

    base = AccountSyncAdapter.normalize(
        profile_payload,
        level_mode=level_mode,
        unknown_policy=unknown_policy,
    )
    provenance = _adjust_legacy_provenance(base) + _audit_raw_sidecar(
        profile_payload, raw_payload
    )
    return AuditedAccountSnapshot(
        base=base,
        provenance=provenance,
        snapshot_id=_snapshot_identity(base, provenance),
    )
