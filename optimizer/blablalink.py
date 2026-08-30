"""Convert the site's BlaBlaLink Worker raw response into an audited account snapshot.

The deployed site Worker returns raw game API rows and keeps its authenticated
BlaBlaLink cookie on the server.  This adapter deliberately does **not** perform
network I/O and never needs an account URL/openid: callers hand it the Worker
JSON already in memory, and the account identifier is discarded.

Conversion uses only repository-canonical mapping tables.  Unknown/missing raw
fields are left incomplete so ``AccountSyncAdapter``/``normalize_account_bundle``
can fail closed instead of silently substituting Moris fixed/max build values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .account_bundle import AuditedAccountSnapshot, normalize_account_bundle


_ROOT = Path(__file__).resolve().parent.parent
_PARTS = (("head", "머리"), ("torso", "몸통"), ("arm", "팔"), ("leg", "다리"))
_CORP_TIER = 10
_NO_ITEM = "없음"


def _load_json(relative: str) -> Any:
    return json.loads((_ROOT / relative).read_text(encoding="utf-8"))


def _name_by_code() -> dict[int, str]:
    raw = _load_json("data/name_codes.json")
    return {int(code): str(name) for code, name in raw.items()}


def _favorite_characters() -> set[str]:
    raw = _load_json("data/parsed_nikke.json")
    return {
        str(name)
        for name, row in raw.items()
        if isinstance(row, Mapping) and row.get("favorite_slots")
    }


def _favorite_grades() -> dict[str, str]:
    raw = _load_json("data/favorite_items.json")
    return {str(key): str(value) for key, value in raw.items()}


def select_blablalink_area(
    worker_payload: Mapping[str, Any],
    *,
    preferred_area: int | None = None,
) -> Mapping[str, Any]:
    """Select one server area without ever retaining the Worker ``openid`` field.

    This mirrors the site's current policy: an explicit area wins; otherwise the
    area with the largest owned-character list is selected.  Ties keep Worker
    order so selection is deterministic for one response.
    """

    areas = worker_payload.get("areas")
    if not isinstance(areas, list) or not areas:
        raise ValueError("BlaBlaLink Worker payload must contain a non-empty `areas` list")

    valid = [area for area in areas if isinstance(area, Mapping)]
    if not valid:
        raise ValueError("BlaBlaLink Worker payload contains no usable area objects")

    if preferred_area is not None:
        for area in valid:
            if int(area.get("area", -1)) == int(preferred_area):
                return area
        raise ValueError(f"requested BlaBlaLink area is absent from Worker response: {preferred_area}")

    return max(
        valid,
        key=lambda area: len(area.get("characters"))
        if isinstance(area.get("characters"), list)
        else -1,
    )


def _equipment(detail: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for api_part, ko_part in _PARTS:
        tier_key = f"{api_part}_equip_tier"
        if tier_key not in detail:
            continue
        tier = int(detail.get(tier_key) or 0)
        if tier >= _CORP_TIER:
            level_key = f"{api_part}_equip_lv"
            if level_key not in detail:
                continue
            out[ko_part] = {"level": int(detail.get(level_key) or 0)}
        elif tier >= 1:
            out[ko_part] = {"tier": f"T{tier}"}
        else:
            out[ko_part] = {"tier": _NO_ITEM}
    return out


def _has_complete_option_slots(detail: Mapping[str, Any]) -> bool:
    return all(
        f"{api_part}_equip_option{slot}_id" in detail
        for api_part, _ in _PARTS
        for slot in (1, 2, 3)
    )


def _skill_levels(detail: Mapping[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, raw_key in (("1", "skill1_lv"), ("2", "skill2_lv"), ("3", "ulti_skill_lv")):
        if raw_key not in detail:
            continue
        value = int(detail.get(raw_key) or 0)
        if 1 <= value <= 10:
            out[key] = value
    return out


def _collection(
    detail: Mapping[str, Any],
    grades: Mapping[str, str],
) -> tuple[str | None, int | None]:
    if "favorite_item_tid" not in detail:
        return None, None
    tid = int(detail.get("favorite_item_tid") or 0)
    if tid == 0:
        return _NO_ITEM, 0
    grade = grades.get(str(tid))
    if grade is None:
        # Keep a calculator-safe placeholder; the raw audit compares non-empty
        # item counts and will mark this conversion UNKNOWN under strict policy.
        return _NO_ITEM, 0
    level = int(detail.get("favorite_item_lv") or 0)
    if grade == "SSR":
        return "SR15", max(1, min(3, level + 1))
    return f"{grade}{max(0, min(15, level))}", 0


def _profile_from_area(area: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from scraper import profile_fetch

    characters = area.get("characters") if isinstance(area.get("characters"), list) else []
    details = area.get("details") if isinstance(area.get("details"), list) else []
    state_effects = (
        area.get("stateEffects") if isinstance(area.get("stateEffects"), list) else None
    )
    if state_effects is None:
        state_effects = (
            area.get("state_effects") if isinstance(area.get("state_effects"), list) else []
        )

    names = _name_by_code()
    favorite_chars = _favorite_characters()
    favorite_grades = _favorite_grades()
    roster_by_code = {
        int(row["name_code"]): row
        for row in characters
        if isinstance(row, Mapping) and row.get("name_code") is not None
    }

    skill_table = profile_fetch._load_equip_skill_table()
    option_map, _, _ = profile_fetch._build_option_map(state_effects, skill_table)

    entries: dict[str, dict[str, Any]] = {}
    for detail in details:
        if not isinstance(detail, Mapping) or detail.get("name_code") is None:
            continue
        code = int(detail["name_code"])
        name = names.get(code)
        if name is None:
            continue
        roster = roster_by_code.get(code, {})
        entry: dict[str, Any] = {}

        if "grade" in roster:
            entry["breakthrough"] = int(roster.get("grade") or 0)
        if "core" in roster:
            entry["core_enhancement"] = int(roster.get("core") or 0)
        if "attractive_lv" in detail:
            entry["affinity"] = max(1, int(detail.get("attractive_lv") or 0))

        entry["skill_levels"] = _skill_levels(detail)
        entry["equipment"] = _equipment(detail)
        if _has_complete_option_slots(detail):
            entry["equip_skills"] = profile_fetch._equip_skills(dict(detail), option_map)

        stage, favorite_stage = _collection(detail, favorite_grades)
        if stage is not None:
            entry["collection_stage"] = stage
        if name in favorite_chars and favorite_stage is not None:
            entry["favorite_stage"] = favorite_stage
        entries[name] = entry

    outpost = area.get("outpost") if isinstance(area.get("outpost"), Mapping) else None
    console_warnings: list[str] = []
    researches = (
        outpost.get("recycle_room_researches")
        if isinstance(outpost, Mapping) and isinstance(outpost.get("recycle_room_researches"), list)
        else []
    )
    console = profile_fetch._console(researches, console_warnings) if researches else None
    cube_names = profile_fetch._load_cube_name_map()

    area_id = area.get("area")
    profile = {
        "_meta": {
            "name": "blablalink-public",
            "area": area_id,
            "source": "blablalink-worker:raw",
            "roster": len(entries),
        },
        "_account": {
            "synchro_level": outpost.get("synchro_level") if isinstance(outpost, Mapping) else None,
            "console": console,
            "console_warnings": console_warnings,
            "cubes": profile_fetch._observed_cubes(details, cube_names),
        },
        "chars": dict(sorted(entries.items())),
    }

    # Deliberately omit Worker `openid`: audit identity is based on build + area,
    # not on a user identifier.  Keep only raw fields needed to prove conversion.
    raw_sidecar = {
        "area": area_id,
        "characters": characters,
        "details": details,
        "state_effects": state_effects,
        # Keep fresh outpost rows for provenance audit. The account identifier is
        # still omitted; this is simulation input, not identity metadata.
        "outpost": outpost,
    }
    return profile, raw_sidecar


def normalize_blablalink_worker_payload(
    worker_payload: Mapping[str, Any],
    *,
    preferred_area: int | None = None,
    level_mode: str = "fixed",
    unknown_policy: str = "error",
) -> AuditedAccountSnapshot:
    """Normalize one in-memory Worker response without retaining account identity.

    No network call is performed.  The input may contain an ``openid`` because
    the deployed Worker currently returns one; this function intentionally never
    copies it into the profile, raw audit sidecar, provenance, or snapshot id.
    """

    area = select_blablalink_area(worker_payload, preferred_area=preferred_area)
    profile, raw_sidecar = _profile_from_area(area)
    return normalize_account_bundle(
        profile,
        raw_sidecar,
        level_mode=level_mode,
        unknown_policy=unknown_policy,
    )
