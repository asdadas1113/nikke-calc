"""Optimizer-facing Enikk composition ingestion using canonical resource ids.

The older report tooling already established the important joining rule: Enikk
thumbnail resource ids match ``scraper/nikke_scraped.json`` ids, while localized
character names are not a safe join key. This module reuses that repository data
contract without importing the report generator or its damage/use-count logic.

Team parse count, external maximum damage, and external average damage are parsed
only to validate the dump token shape and then discarded. They never become
optimizer scores or priorities. Displayed member order defaults to UNKNOWN_ORDER.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from .seed_sources import (
    CompositionOrderKnowledge,
    ExternalCompositionCollection,
    MalformedCompositionRow,
    normalize_labeled_composition,
)

_ROOT = Path(__file__).resolve().parent.parent


def build_enikk_resource_name_map() -> dict[str, str]:
    """Return ``resource id -> canonical Korean calculator name`` from repo data."""

    raw = json.loads((_ROOT / "scraper" / "nikke_scraped.json").read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("scraper/nikke_scraped.json must contain an object")

    out: dict[str, str] = {}
    ambiguous: set[str] = set()
    for name, row in raw.items():
        if not isinstance(row, Mapping) or row.get("id") is None:
            continue
        try:
            key = str(int(row["id"]))
        except (TypeError, ValueError):
            continue
        canonical = str(name)
        previous = out.get(key)
        if previous is None:
            out[key] = canonical
        elif previous != canonical:
            ambiguous.add(key)
    for key in ambiguous:
        out.pop(key, None)
    return out


def collect_enikk_team_dump_compositions(
    text: str,
    *,
    raid: int,
    resource_name_map: Mapping[str, str] | None = None,
    order_knowledge: CompositionOrderKnowledge = CompositionOrderKnowledge.UNKNOWN_ORDER,
) -> ExternalCompositionCollection:
    """Parse the existing ``ids=uses|max|avg`` Teams-tab dump into evidence.

    Resource ids are normalized through ``int`` exactly like the legacy Enikk
    report tool, so a thumbnail id serialized as ``074`` joins repository id
    ``74`` rather than becoming a false unknown.

    No minimum-use cutoff is applied here. If a caller wants to compare a bounded
    public subset, that policy must be explicit outside this parser. Keeping the
    parser threshold-free prevents external popularity from becoming a hidden
    candidate-strength rule.
    """

    if raid <= 0:
        raise ValueError("raid must be positive")
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    source_map = (
        build_enikk_resource_name_map()
        if resource_name_map is None
        else resource_name_map
    )
    name_map: dict[str, str] = {}
    for raw_id, name in source_map.items():
        try:
            normalized_id = str(int(raw_id))
        except (TypeError, ValueError):
            continue
        name_map[normalized_id] = str(name)

    evidence = []
    malformed: list[MalformedCompositionRow] = []

    for row_index, token in enumerate(text.split(), start=1):
        source = f"enikk:S{raid}:teams-row{row_index}"
        try:
            ids_part, metrics_part = token.split("=", 1)
            raw_ids = ids_part.split(",")
            if not raw_ids or any(not value.strip() for value in raw_ids):
                raise ValueError("missing-resource-id")
            ids = tuple(str(int(value.strip())) for value in raw_ids)
            # Validate the legacy dump contract but deliberately discard all three
            # metrics. They are external observations, not optimizer weights.
            metric_parts = metrics_part.split("|")
            if len(metric_parts) != 3:
                raise ValueError("expected uses|max|avg metrics")
            int(metric_parts[0])
            float(metric_parts[1])
            float(metric_parts[2])
            normalized = normalize_labeled_composition(
                ids,
                name_map,
                source=source,
                order_knowledge=order_knowledge,
            )
        except (ValueError, TypeError) as exc:
            malformed.append(MalformedCompositionRow(source, str(exc)))
            continue
        evidence.append(normalized)

    return ExternalCompositionCollection(
        evidence=tuple(evidence),
        malformed_rows=tuple(malformed),
    )
