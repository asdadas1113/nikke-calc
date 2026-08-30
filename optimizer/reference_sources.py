"""Turn external composition evidence into Moris reference hypotheses.

This is deliberately separate from seed adaptation. A seed asks that a known
membership receive search attention; a marginal reference needs one concrete
ordered squad. Proven slot order can be used directly. Membership-only or
unknown-order evidence remains unordered and is handed to bounded placement
exploration in ``reference_discovery``.

External rank, damage, frequency, or tier data is never imported as a score.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .reference_discovery import ReferenceComposition
from .seed_sources import CompositionOrderKnowledge, ExternalCompositionEvidence


@dataclass(frozen=True)
class SkippedReferenceEvidence:
    evidence: ExternalCompositionEvidence
    reason: str


@dataclass(frozen=True)
class ReferenceSourceAdaptation:
    compositions: tuple[ReferenceComposition, ...]
    skipped: tuple[SkippedReferenceEvidence, ...]


def adapt_external_reference_compositions(
    evidence_rows: Sequence[ExternalCompositionEvidence],
    *,
    owned_roster: Sequence[str],
    team_size: int = 5,
) -> ReferenceSourceAdaptation:
    """Keep only complete, owned compositions and preserve order uncertainty.

    Unknown-order duplicate memberships are evaluated once even if many rankers
    used them. Proven-ordered rows deduplicate by exact ordered team. This avoids
    spending Moris calls multiple times merely because an external composition is
    popular; popularity is not a strength bonus.
    """

    if team_size <= 0:
        raise ValueError("team_size must be positive")
    owned = frozenset(str(name) for name in owned_roster)
    if not owned:
        raise ValueError("owned_roster must not be empty")

    compositions: list[ReferenceComposition] = []
    skipped: list[SkippedReferenceEvidence] = []
    seen_ordered: set[tuple[str, ...]] = set()
    seen_membership: set[frozenset[str]] = set()

    for row in evidence_rows:
        if not row.mapping_complete:
            skipped.append(SkippedReferenceEvidence(row, "incomplete-character-mapping"))
            continue
        if len(row.members) != team_size or len(set(row.members)) != team_size:
            skipped.append(SkippedReferenceEvidence(row, "unexpected-or-duplicate-team-size"))
            continue
        missing = tuple(name for name in row.members if name not in owned)
        if missing:
            skipped.append(
                SkippedReferenceEvidence(
                    row,
                    "unowned-members:" + ",".join(missing),
                )
            )
            continue

        if row.order_knowledge is CompositionOrderKnowledge.PROVEN_ORDERED:
            if row.members in seen_ordered:
                continue
            seen_ordered.add(row.members)
            compositions.append(
                ReferenceComposition(
                    members=row.members,
                    source=row.source,
                    order_known=True,
                )
            )
            continue

        membership = frozenset(row.members)
        if membership in seen_membership:
            continue
        seen_membership.add(membership)
        compositions.append(
            ReferenceComposition(
                # The incoming order is retained only as a stable permutation
                # enumeration basis. ``order_known=False`` explicitly prevents it
                # from being interpreted as actual NIKKE slot order.
                members=tuple(row.members),
                source=row.source,
                order_known=False,
            )
        )

    return ReferenceSourceAdaptation(
        compositions=tuple(compositions),
        skipped=tuple(skipped),
    )
