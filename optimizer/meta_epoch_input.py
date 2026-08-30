"""Resolve one unambiguous meta-epoch input mode for a concrete roster.

Benchmark/config parsers may support either:

- pre-derived ``MetaEpochEvidence`` rows; or
- explicit change events whose RESET/NO_RESET/UNCERTAIN effects are already
  curated by an external provenance source.

Both at once is rejected. No epoch input at all returns UNKNOWN evidence for the
whole roster rather than inferring release dates from character existence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from .meta_eligibility import MetaEpochEvidence, MetaEpochKnowledge
from .meta_epoch_registry import derive_meta_epoch_evidence, parse_meta_change_events


def resolve_meta_epoch_input(
    roster: Sequence[str],
    *,
    through: date,
    explicit_epochs: Mapping[str, MetaEpochEvidence] | None = None,
    change_event_rows: Sequence[Mapping[str, Any]] | None = None,
    source: str = "meta-epoch-input",
) -> dict[str, MetaEpochEvidence]:
    """Return one epoch verdict per roster member without silent mode mixing."""

    names = tuple(str(name) for name in roster)
    if len(set(names)) != len(names):
        raise ValueError("roster must contain unique names")
    if not source.strip():
        raise ValueError("source must be non-empty")

    explicit_supplied = explicit_epochs is not None
    events_supplied = change_event_rows is not None
    if explicit_supplied and events_supplied:
        raise ValueError("meta epoch input must use either explicit epochs or change_events, not both")

    if events_supplied:
        events = parse_meta_change_events(tuple(change_event_rows or ()))
        return derive_meta_epoch_evidence(
            names,
            events,
            through=through,
            registry_source=source,
        )

    if explicit_supplied:
        supplied = dict(explicit_epochs or {})
        unknown_names = tuple(name for name in supplied if name not in set(names))
        if unknown_names:
            raise ValueError(
                "explicit meta epochs contain characters outside roster: "
                + ", ".join(sorted(unknown_names))
            )
        out: dict[str, MetaEpochEvidence] = {}
        for name in names:
            row = supplied.get(name)
            if row is None:
                out[name] = MetaEpochEvidence(
                    character=name,
                    knowledge=MetaEpochKnowledge.UNKNOWN,
                    valid_from=None,
                    source=source,
                    reason="no explicit epoch row for owned character",
                )
                continue
            if row.character != name:
                raise ValueError(
                    f"explicit epoch key/character mismatch: key={name!r}, row={row.character!r}"
                )
            out[name] = row
        return out

    return {
        name: MetaEpochEvidence(
            character=name,
            knowledge=MetaEpochKnowledge.UNKNOWN,
            valid_from=None,
            source=source,
            reason="no meta epoch input supplied",
        )
        for name in names
    }
