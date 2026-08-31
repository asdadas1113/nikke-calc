"""First-availability evidence for conservative meta-epoch construction.

A character's initial release / first acquisition window is a mechanically clear
history reset: usage before the character could be acquired is irrelevant.  The
optimizer must not, however, infer that date from resource ids, name-code order,
or current roster metadata.

This module therefore keeps release evidence explicit:

- KNOWN requires an exact ``available_from`` date and becomes a RESET event;
- UNKNOWN carries no date and contributes no synthetic event;
- at most one release record may exist per character in one registry input;
- later confirmed RESET changes (for example a Favorite Item skill replacement)
  may still establish a newer KNOWN epoch even when initial release is UNKNOWN.

The module decides no character strength, usage threshold, or Moris score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from .meta_eligibility import MetaEpochEvidence
from .meta_epoch_registry import (
    MetaChangeEffect,
    MetaChangeEvent,
    derive_meta_epoch_evidence,
)


class FirstAvailabilityKnowledge(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FirstAvailabilityEvidence:
    """Earliest date a character is confirmed to have been acquirable."""

    character: str
    knowledge: FirstAvailabilityKnowledge
    available_from: date | None
    mechanism: str
    source: str

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("first-availability character must be non-empty")
        if not self.mechanism.strip():
            raise ValueError("first-availability mechanism must be non-empty")
        if not self.source.strip():
            raise ValueError("first-availability source must be non-empty")
        if self.knowledge is FirstAvailabilityKnowledge.KNOWN:
            if self.available_from is None:
                raise ValueError("KNOWN first availability requires available_from")
        elif self.available_from is not None:
            raise ValueError("UNKNOWN first availability must not invent a date")


def parse_first_availability_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[FirstAvailabilityEvidence, ...]:
    """Parse explicit release evidence without date/mechanism/source defaults."""

    out: list[FirstAvailabilityEvidence] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"first availability[{index}] must be an object")
        required = ("character", "knowledge", "mechanism", "source")
        missing = tuple(key for key in required if key not in row)
        if missing:
            raise ValueError(
                f"first availability[{index}] missing fields: " + ", ".join(missing)
            )
        character = str(row["character"])
        if character in seen:
            raise ValueError(f"duplicate first-availability character: {character}")
        seen.add(character)
        try:
            knowledge = FirstAvailabilityKnowledge(str(row["knowledge"]))
        except ValueError as exc:
            raise ValueError(
                f"first availability[{index}].knowledge must be known/unknown"
            ) from exc

        available_from = None
        if knowledge is FirstAvailabilityKnowledge.KNOWN:
            if "available_from" not in row:
                raise ValueError(
                    f"first availability[{index}] KNOWN row requires available_from"
                )
            try:
                available_from = date.fromisoformat(str(row["available_from"]))
            except ValueError as exc:
                raise ValueError(
                    f"first availability[{index}].available_from must be ISO YYYY-MM-DD"
                ) from exc
        elif "available_from" in row and row["available_from"] is not None:
            raise ValueError(
                f"first availability[{index}] UNKNOWN row must not contain a date"
            )

        out.append(
            FirstAvailabilityEvidence(
                character=character,
                knowledge=knowledge,
                available_from=available_from,
                mechanism=str(row["mechanism"]),
                source=str(row["source"]),
            )
        )
    return tuple(out)


def release_reset_events(
    releases: Sequence[FirstAvailabilityEvidence],
) -> tuple[MetaChangeEvent, ...]:
    """Convert only confirmed first availability into explicit RESET events."""

    events: list[MetaChangeEvent] = []
    seen: set[str] = set()
    for row in releases:
        if row.character in seen:
            raise ValueError(f"duplicate first-availability character: {row.character}")
        seen.add(row.character)
        if row.knowledge is not FirstAvailabilityKnowledge.KNOWN:
            continue
        if row.available_from is None:
            raise AssertionError("KNOWN first availability lost its date")
        events.append(
            MetaChangeEvent(
                character=row.character,
                effective_on=row.available_from,
                effect=MetaChangeEffect.RESET,
                kind=f"first-availability:{row.mechanism}",
                source=row.source,
            )
        )
    return tuple(events)


def derive_meta_epochs_from_availability_and_changes(
    roster: Sequence[str],
    releases: Sequence[FirstAvailabilityEvidence],
    changes: Sequence[MetaChangeEvent],
    *,
    through: date,
    registry_source: str = "meta-release-change-registry",
) -> dict[str, MetaEpochEvidence]:
    """Combine confirmed first availability and later explicit change evidence.

    Unknown release evidence emits no fake RESET. If no later confirmed RESET is
    available, ``derive_meta_epoch_evidence`` therefore returns UNKNOWN. If a
    later confirmed RESET exists, that event safely becomes the epoch because all
    older usage history is stale regardless of the unknown initial release date.
    """

    names = tuple(str(name) for name in roster)
    roster_set = set(names)
    release_names = {row.character for row in releases}
    unknown_release_names = release_names - roster_set
    if unknown_release_names:
        raise ValueError(
            "first-availability evidence contains characters outside roster: "
            f"{sorted(unknown_release_names)}"
        )
    unknown_change_names = {row.character for row in changes} - roster_set
    if unknown_change_names:
        raise ValueError(
            "meta change evidence contains characters outside roster: "
            f"{sorted(unknown_change_names)}"
        )

    return derive_meta_epoch_evidence(
        names,
        (*release_reset_events(releases), *changes),
        through=through,
        registry_source=registry_source,
    )
