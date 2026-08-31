"""Derive Overload-piece evidence for meta-guided roster filtering.

The calculator-facing profile intentionally aggregates Overload option values
across equipment parts, so it cannot by itself prove that a character has zero
Overload pieces.  The raw profile-sync sidecar still has the twelve per-part
option ids and can prove an exact piece count when those slots are complete.

This module is search-policy metadata only.  It does not modify Moris build
inputs or simulator scores.  Missing/ambiguous evidence fails open: an unknown
Overload state must never be coerced to zero for cold-pool eligibility.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent.parent
_PARTS = ("head", "torso", "arm", "leg")
_SLOTS = (1, 2, 3)


class OverloadKnowledge(str, Enum):
    """Whether account evidence can safely protect or defer a character."""

    ZERO = "zero"
    PRESENT = "present"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OverloadPieceEvidence:
    """Per-character Overload-piece evidence used only by search policy."""

    character: str
    knowledge: OverloadKnowledge
    piece_count: int | None
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("character must be non-empty")
        if self.piece_count is not None and not 0 <= self.piece_count <= len(_PARTS):
            raise ValueError("piece_count must be between 0 and 4 when known")
        if self.knowledge is OverloadKnowledge.ZERO and self.piece_count != 0:
            raise ValueError("ZERO evidence requires piece_count == 0")
        if self.knowledge is OverloadKnowledge.PRESENT and self.piece_count == 0:
            raise ValueError("PRESENT evidence cannot have piece_count == 0")
        if self.knowledge is OverloadKnowledge.UNKNOWN and self.piece_count is not None:
            raise ValueError("UNKNOWN evidence must not invent a piece count")

    @property
    def proven_zero(self) -> bool:
        return self.knowledge is OverloadKnowledge.ZERO and self.piece_count == 0

    @property
    def protected_from_cold_filter(self) -> bool:
        """Only an observed zero is eligible for the separate usage cold test."""

        return not self.proven_zero


def _default_name_by_code() -> dict[int, str]:
    raw = json.loads((_ROOT / "data" / "name_codes.json").read_text(encoding="utf-8"))
    return {int(code): str(name) for code, name in raw.items()}


def _numeric_nonzero(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return any(_numeric_nonzero(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            return float(text) != 0
        except ValueError:
            # Canonical equip_skills are numeric.  An unexpected non-empty value
            # is safer to treat as evidence of presence than as a proven zero.
            return True
    return False


def _profile_proves_presence(entry: Mapping[str, Any]) -> bool:
    skills = entry.get("equip_skills")
    if not isinstance(skills, Mapping):
        return False
    return any(_numeric_nonzero(value) for value in skills.values())


def _option_id_present(value: Any) -> bool | None:
    """Return True/False for a usable raw option id, None when ambiguous."""

    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text) != 0
        except ValueError:
            return None
    return None


def _exact_piece_count(detail: Mapping[str, Any]) -> int | None:
    states: dict[tuple[str, int], bool] = {}
    for part in _PARTS:
        for slot in _SLOTS:
            key = f"{part}_equip_option{slot}_id"
            if key not in detail:
                return None
            present = _option_id_present(detail.get(key))
            if present is None:
                return None
            states[(part, slot)] = present
    return sum(any(states[(part, slot)] for slot in _SLOTS) for part in _PARTS)


def derive_overload_piece_evidence(
    profile_payload: Mapping[str, Any],
    raw_payload: Mapping[str, Any],
    *,
    name_by_code: Mapping[int, str] | None = None,
) -> dict[str, OverloadPieceEvidence]:
    """Derive exact zero/present/unknown evidence without guessing missing data.

    Exact counts come only from a complete set of raw per-part option ids.  A
    non-zero calculator-facing ``equip_skills`` value can still prove that at
    least one Overload option exists when raw detail is incomplete, but it cannot
    recover an exact piece count.  Zero is never inferred from aggregated profile
    values alone.

    ``name_by_code`` exists for tests and alternate importers.  Production use
    defaults to the repository-canonical ``data/name_codes.json`` mapping.
    """

    chars = profile_payload.get("chars")
    if not isinstance(chars, Mapping):
        raise ValueError("profile_payload must contain a `chars` mapping")
    details = raw_payload.get("details")
    if not isinstance(details, list):
        details = []

    names = dict(name_by_code or _default_name_by_code())
    details_by_name: dict[str, list[Mapping[str, Any]]] = {}
    for raw in details:
        if not isinstance(raw, Mapping) or raw.get("name_code") is None:
            continue
        try:
            code = int(raw["name_code"])
        except (TypeError, ValueError):
            continue
        name = names.get(code)
        if name is not None:
            details_by_name.setdefault(name, []).append(raw)

    out: dict[str, OverloadPieceEvidence] = {}
    for character, raw_entry in chars.items():
        name = str(character)
        entry = raw_entry if isinstance(raw_entry, Mapping) else {}
        profile_present = _profile_proves_presence(entry)
        matches = details_by_name.get(name, ())

        if len(matches) != 1:
            if profile_present:
                out[name] = OverloadPieceEvidence(
                    name,
                    OverloadKnowledge.PRESENT,
                    None,
                    "profile:equip_skills",
                    "raw per-part detail is unavailable/ambiguous; aggregated profile still proves at least one Overload option",
                )
            else:
                out[name] = OverloadPieceEvidence(
                    name,
                    OverloadKnowledge.UNKNOWN,
                    None,
                    "profile-sync:raw-sidecar",
                    "raw per-part detail is unavailable/ambiguous, so zero Overload pieces cannot be proven",
                )
            continue

        piece_count = _exact_piece_count(matches[0])
        if piece_count is None:
            if profile_present:
                out[name] = OverloadPieceEvidence(
                    name,
                    OverloadKnowledge.PRESENT,
                    None,
                    "profile:equip_skills",
                    "raw option slots are incomplete; aggregated profile still proves Overload presence",
                )
            else:
                out[name] = OverloadPieceEvidence(
                    name,
                    OverloadKnowledge.UNKNOWN,
                    None,
                    "profile-sync:raw-sidecar",
                    "raw option slots are incomplete, so zero Overload pieces cannot be proven",
                )
            continue

        if piece_count == 0:
            if profile_present:
                out[name] = OverloadPieceEvidence(
                    name,
                    OverloadKnowledge.UNKNOWN,
                    None,
                    "profile+raw:conflict",
                    "profile reports non-zero Overload options while complete raw option ids report zero pieces",
                )
            else:
                out[name] = OverloadPieceEvidence(
                    name,
                    OverloadKnowledge.ZERO,
                    0,
                    "profile-sync:raw-option-slots",
                    "all twelve raw Overload option ids are observed zero",
                )
        else:
            out[name] = OverloadPieceEvidence(
                name,
                OverloadKnowledge.PRESENT,
                piece_count,
                "profile-sync:raw-option-slots",
                "exact Overload piece count derived from complete per-part option ids",
            )
    return out
