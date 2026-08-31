"""Meta-epoch classification using certified lower/upper usage bounds.

This is a parallel strict path to ``meta_eligibility.classify_meta_epoch_usage``.
A character is LOW only when the *worst-case upper bound* of every inspected
season stays at or below the caller's boundary.  It is USED only when observed
lower-bound evidence already exceeds that boundary.  If the boundary lies inside
the uncertainty interval, the verdict is INSUFFICIENT and therefore fails open to
Primary downstream.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from statistics import median

from .cold_pool import UsageClass
from .meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    MetaUsageDecision,
    SoloRaidSchedule,
    post_epoch_completed_raids,
)
from .meta_usage import CharacterUsageWindow
from .meta_usage_bounds import (
    BoundedCharacterUsageWindow,
    CertifiedEnikkSeasonUsageSnapshot,
    aggregate_bounded_character_window,
)


def _upper_bound_window(window: BoundedCharacterUsageWindow) -> CharacterUsageWindow:
    """Adapt audited upper bounds into the existing downstream diagnostic shape."""

    upper_pairs = tuple((raid, upper) for raid, _lower, upper in window.bounds)
    upper_values = [value for _raid, value in upper_pairs]
    positive = tuple(
        raid for raid, lower, _upper in window.bounds if lower > 0
    )
    proven_zero = tuple(
        raid for raid, _lower, upper in window.bounds if upper == 0
    )
    return CharacterUsageWindow(
        character=window.character,
        requested_eligible_raids=window.requested_eligible_raids,
        usable_raids=window.usable_raids,
        uncertain_raids=window.uncertain_raids,
        positive_raids=positive,
        zero_raids=proven_zero,
        usage_fractions=upper_pairs,
        peak_usage=max(upper_values) if upper_values else None,
        median_usage=float(median(upper_values)) if upper_values else None,
    )


def classify_meta_epoch_usage_bounded(
    character: str,
    snapshots: Iterable[CertifiedEnikkSeasonUsageSnapshot],
    *,
    epoch: MetaEpochEvidence,
    schedule: SoloRaidSchedule,
    completed_through: date,
    policy: LowUsagePolicy,
) -> MetaUsageDecision:
    """Classify one character from certified cohort bounds, never point estimates."""

    name = str(character)
    if epoch.character != name:
        raise ValueError("meta epoch character does not match classification target")

    def decision(
        classification: UsageClass,
        reason: str,
        *,
        eligible: tuple[int, ...] = (),
        inspected: tuple[int, ...] = (),
        window: CharacterUsageWindow | None = None,
    ) -> MetaUsageDecision:
        return MetaUsageDecision(
            character=name,
            classification=classification,
            reason=reason,
            eligible_post_epoch_raids=eligible,
            inspected_raids=inspected,
            window=window,
            epoch=epoch,
            schedule_source=schedule.source,
            policy=policy,
        )

    if epoch.knowledge is not MetaEpochKnowledge.KNOWN:
        return decision(
            UsageClass.INSUFFICIENT,
            f"meta-epoch-{epoch.knowledge.value}-fail-open",
        )
    if not schedule.complete:
        return decision(
            UsageClass.INSUFFICIENT,
            "raid-schedule-incomplete-fail-open",
        )

    eligible = post_epoch_completed_raids(
        epoch,
        schedule,
        completed_through=completed_through,
    )
    if len(eligible) < policy.completed_seasons:
        return decision(
            UsageClass.INSUFFICIENT,
            "insufficient-completed-post-epoch-raids",
            eligible=eligible,
        )

    inspected = eligible[-policy.completed_seasons :]
    bounded = aggregate_bounded_character_window(
        name,
        snapshots,
        eligible_raids=inspected,
    )
    upper_window = _upper_bound_window(bounded)
    if (
        not bounded.complete_for_requested_window
        or bounded.peak_lower_usage is None
        or bounded.peak_upper_usage is None
    ):
        return decision(
            UsageClass.INSUFFICIENT,
            "bounded-usage-window-incomplete-fail-open",
            eligible=eligible,
            inspected=inspected,
            window=upper_window,
        )

    if bounded.peak_upper_usage <= policy.max_peak_usage:
        return decision(
            UsageClass.LOW,
            "complete-post-epoch-upper-bound-below-peak-boundary",
            eligible=eligible,
            inspected=inspected,
            window=upper_window,
        )

    if bounded.peak_lower_usage > policy.max_peak_usage:
        return decision(
            UsageClass.USED,
            "post-epoch-lower-bound-exceeds-peak-boundary",
            eligible=eligible,
            inspected=inspected,
            window=upper_window,
        )

    return decision(
        UsageClass.INSUFFICIENT,
        "usage-bound-crosses-peak-boundary-fail-open",
        eligible=eligible,
        inspected=inspected,
        window=upper_window,
    )
