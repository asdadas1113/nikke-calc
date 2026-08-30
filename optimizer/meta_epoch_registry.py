"""Derive Cold-safe meta epochs from externally curated change events.

This module still does not decide whether a patch is "large." A source adapter or
curated registry supplies that judgment explicitly as RESET / NO_RESET /
UNCERTAIN. The optimizer only applies conservative chronology:

- the latest confirmed RESET (release counts as RESET) is the epoch;
- a later UNCERTAIN-impact event invalidates confidence and returns UNCERTAIN;
- a later confirmed NO_RESET event leaves the epoch unchanged;
- no confirmed RESET evidence returns UNKNOWN.

Thus an ambiguous rebalance can only protect a character from Cold; it cannot make
old low-usage history look stronger.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

from .meta_eligibility import MetaEpochEvidence, MetaEpochKnowledge


class MetaChangeEffect(str, Enum):
    RESET = "reset"
    NO_RESET = "no_reset"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class MetaChangeEvent:
    character: str
    effective_on: date
    effect: MetaChangeEffect
    kind: str
    source: str

    def __post_init__(self) -> None:
        if not self.character:
            raise ValueError("meta change character must be non-empty")
        if not self.kind.strip():
            raise ValueError("meta change kind must be non-empty")
        if not self.source.strip():
            raise ValueError("meta change source must be non-empty")


def parse_meta_change_events(rows: Sequence[Mapping[str, Any]]) -> tuple[MetaChangeEvent, ...]:
    """Parse explicit event records; no effect/kind/date defaults are invented."""

    events: list[MetaChangeEvent] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"meta change event[{index}] must be an object")
        required = ("character", "effective_on", "effect", "kind", "source")
        missing = tuple(key for key in required if key not in row)
        if missing:
            raise ValueError(
                f"meta change event[{index}] missing fields: " + ", ".join(missing)
            )
        try:
            effective_on = date.fromisoformat(str(row["effective_on"]))
        except ValueError as exc:
            raise ValueError(
                f"meta change event[{index}].effective_on must be ISO YYYY-MM-DD"
            ) from exc
        try:
            effect = MetaChangeEffect(str(row["effect"]))
        except ValueError as exc:
            raise ValueError(
                f"meta change event[{index}].effect must be reset/no_reset/uncertain"
            ) from exc
        events.append(
            MetaChangeEvent(
                character=str(row["character"]),
                effective_on=effective_on,
                effect=effect,
                kind=str(row["kind"]),
                source=str(row["source"]),
            )
        )
    return tuple(events)


def derive_meta_epoch_evidence(
    roster: Sequence[str],
    events: Iterable[MetaChangeEvent],
    *,
    through: date,
    registry_source: str = "meta-change-registry",
) -> dict[str, MetaEpochEvidence]:
    """Return one conservative epoch verdict for every roster character."""

    if not registry_source.strip():
        raise ValueError("registry_source must be non-empty")
    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster must contain unique names")
    grouped: dict[str, list[MetaChangeEvent]] = {name: [] for name in names}
    for event in events:
        if event.character in grouped and event.effective_on <= through:
            grouped[event.character].append(event)

    out: dict[str, MetaEpochEvidence] = {}
    for name in names:
        rows = sorted(
            grouped[name],
            key=lambda row: (row.effective_on, row.effect.value, row.kind, row.source),
        )
        resets = [row for row in rows if row.effect is MetaChangeEffect.RESET]
        if not resets:
            uncertain = [row for row in rows if row.effect is MetaChangeEffect.UNCERTAIN]
            if uncertain:
                latest = uncertain[-1]
                out[name] = MetaEpochEvidence(
                    character=name,
                    knowledge=MetaEpochKnowledge.UNCERTAIN,
                    valid_from=None,
                    source=latest.source,
                    reason=(
                        "no confirmed history reset and change impact remains uncertain: "
                        f"{latest.kind} on {latest.effective_on.isoformat()}"
                    ),
                )
            else:
                out[name] = MetaEpochEvidence(
                    character=name,
                    knowledge=MetaEpochKnowledge.UNKNOWN,
                    valid_from=None,
                    source=registry_source,
                    reason="no confirmed history-reset event",
                )
            continue

        latest_reset = max(resets, key=lambda row: row.effective_on)
        later_uncertain = [
            row
            for row in rows
            if row.effect is MetaChangeEffect.UNCERTAIN
            and row.effective_on > latest_reset.effective_on
        ]
        if later_uncertain:
            latest = later_uncertain[-1]
            out[name] = MetaEpochEvidence(
                character=name,
                knowledge=MetaEpochKnowledge.UNCERTAIN,
                valid_from=None,
                source=latest.source,
                reason=(
                    "change after latest confirmed reset has uncertain history impact: "
                    f"{latest.kind} on {latest.effective_on.isoformat()}"
                ),
            )
            continue

        out[name] = MetaEpochEvidence(
            character=name,
            knowledge=MetaEpochKnowledge.KNOWN,
            valid_from=latest_reset.effective_on,
            source=latest_reset.source,
            reason=(
                f"latest confirmed history reset: {latest_reset.kind} on "
                f"{latest_reset.effective_on.isoformat()}"
            ),
        )
    return out
