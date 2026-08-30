"""Convert external squad-composition evidence into exploration-only seeds.

External sites can reliably tell us that certain members appeared together even
when their displayed/serialized order is not documented as in-game slot order.
This boundary keeps that uncertainty explicit:

- only PROVEN_ORDERED evidence may become ``ExactCompSeed``;
- MEMBERSHIP_ONLY or UNKNOWN_ORDER evidence becomes a full-membership ``CoreSeed``;
- incomplete/ambiguous mapping is skipped rather than guessed.

No external rank, damage, frequency, or tier value is accepted here. The output
only controls which hypotheses receive evaluator attention; Moris remains the
score source and the final allocator receives no source bonus.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .seeds import CoreSeed, ExactCompSeed


class CompositionOrderKnowledge(str, Enum):
    """What an external source proves about the listed member order."""

    PROVEN_ORDERED = "proven_ordered"
    MEMBERSHIP_ONLY = "membership_only"
    UNKNOWN_ORDER = "unknown_order"


@dataclass(frozen=True)
class ExternalCompositionEvidence:
    """Mapped membership evidence with explicit order provenance."""

    members: tuple[str, ...]
    order_knowledge: CompositionOrderKnowledge
    source: str
    mapping_complete: bool = True
    unmapped_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("composition source must be non-empty")
        if len(set(self.members)) != len(self.members):
            raise ValueError("mapped composition members must be unique")
        if self.mapping_complete and self.unmapped_labels:
            raise ValueError("complete mapping must not retain unmapped labels")
        if not self.mapping_complete and not self.unmapped_labels:
            raise ValueError("incomplete mapping must identify unmapped labels")


@dataclass(frozen=True)
class SkippedCompositionEvidence:
    evidence: ExternalCompositionEvidence
    reason: str


@dataclass(frozen=True)
class SeedSourceAdaptation:
    exact_seeds: tuple[ExactCompSeed, ...]
    core_seeds: tuple[CoreSeed, ...]
    skipped: tuple[SkippedCompositionEvidence, ...]


def normalize_labeled_composition(
    labels: Sequence[Any],
    name_map: Mapping[str, str],
    *,
    source: str,
    order_knowledge: CompositionOrderKnowledge = CompositionOrderKnowledge.UNKNOWN_ORDER,
) -> ExternalCompositionEvidence:
    """Map external labels without fuzzy fallback or last-write-wins guessing."""

    if isinstance(labels, (str, bytes)):
        raise ValueError("composition labels must be a sequence, not text")

    members: list[str] = []
    unmapped: list[str] = []
    for raw in labels:
        label = str(raw)
        canonical = name_map.get(label)
        if canonical is None:
            unmapped.append(label)
            continue
        name = str(canonical)
        if name in members:
            raise ValueError("mapped composition contains duplicate canonical members")
        members.append(name)

    return ExternalCompositionEvidence(
        members=tuple(members),
        order_knowledge=order_knowledge,
        source=source,
        mapping_complete=not unmapped,
        unmapped_labels=tuple(dict.fromkeys(unmapped)),
    )


def normalize_enikk_sr_team(
    team: Mapping[str, Any],
    name_map: Mapping[str, str],
    *,
    source: str,
    order_knowledge: CompositionOrderKnowledge = CompositionOrderKnowledge.UNKNOWN_ORDER,
) -> ExternalCompositionEvidence:
    """Normalize one Enikk ``SRRankings.teams`` row conservatively.

    Enikk exposes ``team["characters"]`` as a sequence, but this adapter does not
    infer that serialization order equals NIKKE slot order. Until source-specific
    evidence proves that contract, the default is ``UNKNOWN_ORDER`` and therefore
    the row can only nominate a membership CoreSeed.
    """

    if not isinstance(team, Mapping):
        raise ValueError("Enikk team row must be a mapping")
    labels = team.get("characters")
    if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)):
        raise ValueError("Enikk team row must contain a character sequence")
    return normalize_labeled_composition(
        labels,
        name_map,
        source=source,
        order_knowledge=order_knowledge,
    )


def adapt_external_compositions(
    evidence_rows: Sequence[ExternalCompositionEvidence],
    *,
    team_size: int = 5,
) -> SeedSourceAdaptation:
    """Create seeds while preserving the evidence boundary.

    A full five-member CoreSeed is intentional: its semantics are membership only,
    so it can protect any caller-supplied ordered candidate with exactly that core
    without inventing one of the 5! placements here.
    """

    if team_size <= 0:
        raise ValueError("team_size must be positive")

    exact: list[ExactCompSeed] = []
    cores: list[CoreSeed] = []
    skipped: list[SkippedCompositionEvidence] = []
    seen_exact: set[tuple[str, ...]] = set()
    seen_core: set[frozenset[str]] = set()

    for row in evidence_rows:
        if not row.mapping_complete:
            skipped.append(SkippedCompositionEvidence(row, "incomplete-character-mapping"))
            continue
        if len(row.members) != team_size:
            skipped.append(SkippedCompositionEvidence(row, "unexpected-team-size"))
            continue
        if len(set(row.members)) != team_size:
            skipped.append(SkippedCompositionEvidence(row, "duplicate-team-member"))
            continue

        if row.order_knowledge is CompositionOrderKnowledge.PROVEN_ORDERED:
            if row.members in seen_exact:
                continue
            seen_exact.add(row.members)
            exact.append(ExactCompSeed(row.members, source=row.source))
            continue

        membership = frozenset(row.members)
        if membership in seen_core:
            continue
        seen_core.add(membership)
        # Stable lexical order is only a deterministic representation. CoreSeed
        # itself treats members as membership constraints, never slot placement.
        cores.append(CoreSeed(tuple(sorted(membership)), source=row.source))

    return SeedSourceAdaptation(
        exact_seeds=tuple(exact),
        core_seeds=tuple(cores),
        skipped=tuple(skipped),
    )
