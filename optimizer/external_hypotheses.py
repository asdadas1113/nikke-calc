"""Build score-neutral optimizer hypotheses from one external evidence set.

Seeds and marginal references serve different search roles, but they must not
silently interpret the same public composition differently. This module applies
shared ownership/team-size gates once, then derives both seed hypotheses and
reference-placement hypotheses from the same surviving evidence rows.

No external damage, rank, parse count, or popularity value is accepted here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .reference_sources import ReferenceSourceAdaptation, adapt_external_reference_compositions
from .seed_sources import (
    ExternalCompositionEvidence,
    SeedSourceAdaptation,
    SkippedCompositionEvidence,
    adapt_external_compositions,
)


@dataclass(frozen=True)
class SkippedOwnedComposition:
    evidence: ExternalCompositionEvidence
    reason: str


@dataclass(frozen=True)
class ExternalHypothesisPlan:
    seeds: SeedSourceAdaptation
    references: ReferenceSourceAdaptation
    skipped_before_adaptation: tuple[SkippedOwnedComposition, ...]


def build_external_hypothesis_plan(
    evidence_rows: Sequence[ExternalCompositionEvidence],
    *,
    owned_roster: Sequence[str],
    team_size: int = 5,
) -> ExternalHypothesisPlan:
    """Gate one evidence set once, then derive both search channels.

    Incomplete mappings, wrong-sized rows, and unowned memberships are excluded
    visibly before either channel. An unowned public composition is never patched
    with a guessed replacement. Order uncertainty is preserved by the downstream
    seed/reference adapters.
    """

    if team_size <= 0:
        raise ValueError("team_size must be positive")
    owned = frozenset(str(name) for name in owned_roster)
    if not owned:
        raise ValueError("owned_roster must not be empty")

    accepted: list[ExternalCompositionEvidence] = []
    skipped: list[SkippedOwnedComposition] = []
    for row in evidence_rows:
        if not row.mapping_complete:
            skipped.append(SkippedOwnedComposition(row, "incomplete-character-mapping"))
            continue
        if len(row.members) != team_size or len(set(row.members)) != team_size:
            skipped.append(SkippedOwnedComposition(row, "unexpected-or-duplicate-team-size"))
            continue
        missing = tuple(name for name in row.members if name not in owned)
        if missing:
            skipped.append(
                SkippedOwnedComposition(
                    row,
                    "unowned-members:" + ",".join(missing),
                )
            )
            continue
        accepted.append(row)

    seeds = adapt_external_compositions(tuple(accepted), team_size=team_size)
    references = adapt_external_reference_compositions(
        tuple(accepted),
        owned_roster=tuple(owned),
        team_size=team_size,
    )
    # Shared pre-gates should leave no ordinary adaptation skips. Keep the fields
    # intact anyway so future adapter-specific checks remain visible rather than
    # being silently discarded.
    return ExternalHypothesisPlan(
        seeds=seeds,
        references=references,
        skipped_before_adaptation=tuple(skipped),
    )
