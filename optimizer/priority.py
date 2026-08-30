"""Score-blind ordering helpers for budgeted marginal measurement."""

from __future__ import annotations

from collections.abc import Iterable

from .marginal import CandidateMarginalPlan, CandidateMarginalPlanEntry


def reorder_candidate_marginal_plan(
    plan: CandidateMarginalPlan,
    candidate_order: Iterable[str],
) -> CandidateMarginalPlan:
    """Return the same marginal work plan with a different execution order.

    Reference-team assignment and replacement-slot choices are preserved exactly.
    Only ``entries`` order changes, which lets low-budget experiments vary which
    candidates are measured first without silently changing their marginal
    contexts.

    ``candidate_order`` may be partial. Listed candidates are moved to the front
    in the supplied order; all remaining planned candidates keep their original
    relative order. Unknown or duplicate names are rejected so a priority policy
    cannot silently disappear or duplicate work.
    """

    entries_by_candidate: dict[str, CandidateMarginalPlanEntry] = {
        entry.candidate: entry for entry in plan.entries
    }
    requested = tuple(candidate_order)
    if len(set(requested)) != len(requested):
        raise ValueError("candidate_order must not contain duplicates")

    unknown = tuple(name for name in requested if name not in entries_by_candidate)
    if unknown:
        raise ValueError(f"candidate_order contains unplanned candidates: {unknown}")

    requested_set = set(requested)
    ordered_entries = [entries_by_candidate[name] for name in requested]
    ordered_entries.extend(
        entry for entry in plan.entries if entry.candidate not in requested_set
    )

    return CandidateMarginalPlan(
        reference_teams=plan.reference_teams,
        entries=tuple(ordered_entries),
        unplanned_candidates=plan.unplanned_candidates,
    )
