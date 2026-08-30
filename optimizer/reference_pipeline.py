"""Common external-reference preparation before Pure/Meta search comparison.

Reference placement discovery is account/boss dependent but does not belong to
Pure or Meta roster policy. It is therefore prepared once from the full owned
account and can be shared by both modes. Its Moris call cost stays explicit so an
end-to-end benchmark can report ``common reference calls + mode calls`` rather
than hiding setup work.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .budget import SearchBudget
from .evaluator import MorisEvaluator
from .external_hypotheses import ExternalHypothesisPlan, build_external_hypothesis_plan
from .reference_discovery import ReferenceDiscoveryResult, discover_reference_placements
from .seed_sources import ExternalCompositionEvidence


@dataclass(frozen=True)
class ExternalReferencePreparation:
    hypotheses: ExternalHypothesisPlan
    discovery: ReferenceDiscoveryResult

    @property
    def references(self) -> tuple[tuple[str, ...], ...]:
        return self.discovery.selected_references

    @property
    def common_simulate_calls(self) -> int:
        return self.discovery.simulate_calls


def prepare_external_references(
    evaluator: MorisEvaluator,
    evidence_rows: Sequence[ExternalCompositionEvidence],
    *,
    owned_roster: Sequence[str],
    budget: SearchBudget,
    max_placements_per_composition: int,
    team_size: int = 5,
    legal=None,
    evaluate_kwargs: dict | None = None,
) -> ExternalReferencePreparation:
    """Prepare shared seeds/reference hypotheses and choose ordered Moris refs.

    Ownership/mapping/team-size gates are shared with seed creation. Only the
    surviving reference hypotheses consume Moris calls. Unknown-order membership
    receives bounded placement exploration; proven order receives exactly one
    ordered hypothesis. The placement budget must be large enough to give every
    viable composition one uncached look, enforced by reference discovery.
    """

    hypotheses = build_external_hypothesis_plan(
        evidence_rows,
        owned_roster=owned_roster,
        team_size=team_size,
    )
    discovery = discover_reference_placements(
        evaluator,
        hypotheses.references.compositions,
        budget=budget,
        max_per_composition=max_placements_per_composition,
        legal=legal,
        evaluate_kwargs=evaluate_kwargs,
    )
    return ExternalReferencePreparation(
        hypotheses=hypotheses,
        discovery=discovery,
    )
