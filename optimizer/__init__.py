"""Roster optimizer prototype built around the Moris simulator evaluator.

The package-level Meta/Cold API is production-oriented and therefore uses
certified bounded usage evidence by default.  Descriptive point-estimate helpers
remain available only through explicit ``Research*`` / ``research_*`` names.
"""

from .account import (
    AccountSnapshot,
    AccountSyncAdapter,
    FieldProvenance,
    ProvenanceStatus,
    normalize_account_sync,
)
from .account_bundle import AuditedAccountSnapshot, normalize_account_bundle
from .anytime import (
    AnytimeSearchResult,
    AnytimeStageMetrics,
    CandidateDiscoveryContext,
    run_anytime_search_round,
)
from .automatic_search import (
    AutomaticDiscoveryPolicy,
    AutomaticPlacementMode,
    AutomaticSearchResult,
    run_automatic_anytime_search_round,
)
from .blablalink import normalize_blablalink_worker_payload, select_blablalink_area
from .budget import BudgetedEvaluator, SearchBudget, SearchBudgetExhausted
from .candidate_generation import (
    AllocationCandidateGenerationResult,
    CandidateGenerationResult,
    GeneratedCandidate,
    GeneratedProxyAllocation,
    all_permutation_placements,
    generate_additive_allocation_beam_candidates,
    generate_additive_beam_candidates,
    identity_placement,
)
from .candidates import CandidateTeam
from .cold_exploration import (
    ColdExplorationPick,
    ColdExplorationPlan,
    plan_cold_exploration,
)
from .cold_pool import (
    ColdDecision,
    ColdPoolPartition,
    ColdRestorationResult,
    RestorationStep,
    SoloRaidUsageEvidence,
    StructuralDemand,
    StructuralFeasibility,
    UsageClass,
    build_burst_role_map,
    check_structural_feasibility,
    partition_meta_guided_roster,
    restore_cold_until_feasible,
)
from .constraints import (
    BurstMetadata,
    BurstStructureReport,
    BurstStructureValidator,
    ConstraintSet,
    TeamRequirement,
    teams_are_disjoint,
)
from .discovery import (
    CandidateDiscoveryBundle,
    MultiViewCandidateDiscovery,
    SkippedDiscoveryView,
    generate_candidate_discovery_bundle,
    generate_multi_view_candidate_discovery,
)
from .enikk_sources import (
    build_enikk_resource_name_map,
    collect_enikk_team_dump_compositions,
)
from .evaluator import (
    CacheIdentity,
    Evaluation,
    EvaluationTimings,
    EvaluatorStats,
    MorisEvaluator,
)
from .external_hypotheses import (
    ExternalHypothesisPlan,
    SkippedOwnedComposition,
    build_external_hypothesis_plan,
)
from .global_search import Allocation, select_global_allocation
from .marginal import (
    CandidateMarginalPlan,
    CandidateMarginalPlanEntry,
    MarginalMeasurement,
    MarginalObservation,
    MarginalValue,
    measure_marginals,
    measure_marginals_with_candidates,
    measure_planned_marginals_with_candidates,
    plan_candidate_specific_marginals,
)
from .meta_availability import (
    AvailabilityKnowledge,
    FirstPositiveAvailability,
    completed_raids_after_first_positive,
    derive_first_positive_availability,
    derive_roster_first_positive_availability,
)
from .meta_eligibility import (
    LowUsagePolicy,
    MetaEpochEvidence,
    MetaEpochKnowledge,
    MetaUsageDecision,
    SoloRaidPeriod,
    SoloRaidSchedule,
    classify_meta_epoch_usage as research_classify_meta_epoch_usage,
    post_epoch_completed_raids,
    to_solo_raid_usage_evidence,
)
from .meta_eligibility_bounds import classify_meta_epoch_usage_bounded
from .meta_policy import (
    MetaGuidedPartitionResult,
    MetaUsageRosterResult,
    PreparedMetaGuidedRoster,
    PreparedMetaGuidedSearchRoster,
    build_meta_guided_partition as research_build_meta_guided_partition,
    classify_roster_meta_usage as research_classify_roster_meta_usage,
    prepare_meta_guided_roster as research_prepare_meta_guided_roster,
    prepare_meta_guided_search_roster as research_prepare_meta_guided_search_roster,
)
from .meta_policy_bounds import (
    build_meta_guided_partition_bounded,
    classify_roster_meta_usage_bounded,
    prepare_meta_guided_roster_bounded,
    prepare_meta_guided_search_roster_bounded,
)
from .meta_usage import (
    CharacterUsageWindow as ResearchCharacterUsageWindow,
    EnikkSeasonUsageSnapshot as ResearchEnikkSeasonUsageSnapshot,
    ExternalNameMapping,
    SeasonUsageObservation as ResearchSeasonUsageObservation,
    aggregate_character_window as research_aggregate_character_window,
    build_external_name_mapping,
    summarize_enikk_rankings as research_summarize_enikk_rankings,
)
from .meta_usage_bounds import (
    BoundedCharacterUsageWindow,
    BoundedSeasonUsageObservation,
    CertifiedEnikkSeasonUsageSnapshot,
    RankingCoverageContract,
    aggregate_bounded_character_window,
    certify_enikk_rankings,
)
from .overload import (
    OverloadKnowledge,
    OverloadPieceEvidence,
    derive_overload_piece_evidence,
)
from .pipeline import (
    AllocationRefinementResult,
    PipelineStageMetrics,
    evaluate_allocation_with_one_swap_refinement,
)
from .priority import reorder_candidate_marginal_plan
from .proxy_views import (
    ProxyView,
    ProxyViewCandidate,
    ProxyViewHit,
    build_planned_marginal_prefix_views,
    select_proxy_view_candidates,
)
from .reference_discovery import (
    EvaluatedReferencePlacement,
    ReferenceComposition,
    ReferenceDiscoveryResult,
    balanced_placement_order,
    discover_reference_placements,
    ensure_marginal_reference_coverage,
)
from .reference_pipeline import ExternalReferencePreparation, prepare_external_references
from .reference_sources import (
    ReferenceSourceAdaptation,
    SkippedReferenceEvidence,
    adapt_external_reference_compositions,
)
from .refinement import OneSwapNeighbor, generate_one_swap_neighbors
from .same_budget import (
    InvalidSameBudgetComparison,
    SameBudgetComparison,
    SearchRunMetrics,
    SearchStageCalls,
    run_same_budget_comparison,
)
from .seed_sources import (
    CompositionOrderKnowledge,
    ExternalCompositionCollection,
    ExternalCompositionEvidence,
    MalformedCompositionRow,
    SeedSourceAdaptation,
    SkippedCompositionEvidence,
    adapt_external_compositions,
    collect_enikk_sr_compositions,
    normalize_enikk_sr_team,
    normalize_labeled_composition,
)
from .seeds import (
    CoreSeed,
    ExactCompSeed,
    SeedCandidate,
    SeedSelection,
    select_seed_candidates,
)
from .synergy import PairSynergyObservation, PairSynergyProbe, measure_pair_probes
from .validation import ValidationMetrics, enumerate_legal_teams, run_exhaustive_validation
from .worker_account import WorkerAccountBundle, build_worker_account_bundle

# Production package-level Meta API: certified bounded evidence only.
classify_meta_epoch_usage = classify_meta_epoch_usage_bounded
classify_roster_meta_usage = classify_roster_meta_usage_bounded
build_meta_guided_partition = build_meta_guided_partition_bounded
prepare_meta_guided_roster = prepare_meta_guided_roster_bounded
prepare_meta_guided_search_roster = prepare_meta_guided_search_roster_bounded

__all__ = [
    "AccountSnapshot",
    "AccountSyncAdapter",
    "Allocation",
    "AllocationCandidateGenerationResult",
    "AllocationRefinementResult",
    "AnytimeSearchResult",
    "AnytimeStageMetrics",
    "AuditedAccountSnapshot",
    "AutomaticDiscoveryPolicy",
    "AutomaticPlacementMode",
    "AutomaticSearchResult",
    "AvailabilityKnowledge",
    "BoundedCharacterUsageWindow",
    "BoundedSeasonUsageObservation",
    "BudgetedEvaluator",
    "BurstMetadata",
    "BurstStructureReport",
    "BurstStructureValidator",
    "CacheIdentity",
    "CandidateDiscoveryBundle",
    "CandidateDiscoveryContext",
    "CandidateGenerationResult",
    "CandidateMarginalPlan",
    "CandidateMarginalPlanEntry",
    "CandidateTeam",
    "CertifiedEnikkSeasonUsageSnapshot",
    "ColdDecision",
    "ColdExplorationPick",
    "ColdExplorationPlan",
    "ColdPoolPartition",
    "ColdRestorationResult",
    "CompositionOrderKnowledge",
    "ConstraintSet",
    "CoreSeed",
    "EvaluatedReferencePlacement",
    "Evaluation",
    "EvaluationTimings",
    "EvaluatorStats",
    "ExactCompSeed",
    "ExternalCompositionCollection",
    "ExternalCompositionEvidence",
    "ExternalHypothesisPlan",
    "ExternalNameMapping",
    "ExternalReferencePreparation",
    "FieldProvenance",
    "FirstPositiveAvailability",
    "GeneratedCandidate",
    "GeneratedProxyAllocation",
    "InvalidSameBudgetComparison",
    "LowUsagePolicy",
    "MalformedCompositionRow",
    "MarginalMeasurement",
    "MarginalObservation",
    "MarginalValue",
    "MetaEpochEvidence",
    "MetaEpochKnowledge",
    "MetaGuidedPartitionResult",
    "MetaUsageDecision",
    "MetaUsageRosterResult",
    "MorisEvaluator",
    "MultiViewCandidateDiscovery",
    "OneSwapNeighbor",
    "OverloadKnowledge",
    "OverloadPieceEvidence",
    "PairSynergyObservation",
    "PairSynergyProbe",
    "PipelineStageMetrics",
    "PreparedMetaGuidedRoster",
    "PreparedMetaGuidedSearchRoster",
    "ProvenanceStatus",
    "ProxyView",
    "ProxyViewCandidate",
    "ProxyViewHit",
    "RankingCoverageContract",
    "ReferenceComposition",
    "ReferenceDiscoveryResult",
    "ReferenceSourceAdaptation",
    "ResearchCharacterUsageWindow",
    "ResearchEnikkSeasonUsageSnapshot",
    "ResearchSeasonUsageObservation",
    "RestorationStep",
    "SameBudgetComparison",
    "SearchBudget",
    "SearchBudgetExhausted",
    "SearchRunMetrics",
    "SearchStageCalls",
    "SeedCandidate",
    "SeedSelection",
    "SeedSourceAdaptation",
    "SkippedCompositionEvidence",
    "SkippedDiscoveryView",
    "SkippedOwnedComposition",
    "SkippedReferenceEvidence",
    "SoloRaidPeriod",
    "SoloRaidSchedule",
    "SoloRaidUsageEvidence",
    "StructuralDemand",
    "StructuralFeasibility",
    "TeamRequirement",
    "UsageClass",
    "ValidationMetrics",
    "WorkerAccountBundle",
    "adapt_external_compositions",
    "adapt_external_reference_compositions",
    "aggregate_bounded_character_window",
    "all_permutation_placements",
    "balanced_placement_order",
    "build_burst_role_map",
    "build_enikk_resource_name_map",
    "build_external_hypothesis_plan",
    "build_external_name_mapping",
    "build_meta_guided_partition",
    "build_meta_guided_partition_bounded",
    "build_planned_marginal_prefix_views",
    "build_worker_account_bundle",
    "certify_enikk_rankings",
    "check_structural_feasibility",
    "classify_meta_epoch_usage",
    "classify_meta_epoch_usage_bounded",
    "classify_roster_meta_usage",
    "classify_roster_meta_usage_bounded",
    "collect_enikk_sr_compositions",
    "collect_enikk_team_dump_compositions",
    "completed_raids_after_first_positive",
    "derive_first_positive_availability",
    "derive_overload_piece_evidence",
    "derive_roster_first_positive_availability",
    "discover_reference_placements",
    "ensure_marginal_reference_coverage",
    "enumerate_legal_teams",
    "evaluate_allocation_with_one_swap_refinement",
    "generate_additive_allocation_beam_candidates",
    "generate_additive_beam_candidates",
    "generate_candidate_discovery_bundle",
    "generate_multi_view_candidate_discovery",
    "generate_one_swap_neighbors",
    "identity_placement",
    "measure_marginals",
    "measure_marginals_with_candidates",
    "measure_pair_probes",
    "measure_planned_marginals_with_candidates",
    "normalize_account_bundle",
    "normalize_account_sync",
    "normalize_blablalink_worker_payload",
    "normalize_enikk_sr_team",
    "normalize_labeled_composition",
    "partition_meta_guided_roster",
    "plan_candidate_specific_marginals",
    "plan_cold_exploration",
    "post_epoch_completed_raids",
    "prepare_external_references",
    "prepare_meta_guided_roster",
    "prepare_meta_guided_roster_bounded",
    "prepare_meta_guided_search_roster",
    "prepare_meta_guided_search_roster_bounded",
    "reorder_candidate_marginal_plan",
    "research_aggregate_character_window",
    "research_build_meta_guided_partition",
    "research_classify_meta_epoch_usage",
    "research_classify_roster_meta_usage",
    "research_prepare_meta_guided_roster",
    "research_prepare_meta_guided_search_roster",
    "research_summarize_enikk_rankings",
    "restore_cold_until_feasible",
    "run_automatic_anytime_search_round",
    "run_anytime_search_round",
    "run_exhaustive_validation",
    "run_same_budget_comparison",
    "select_blablalink_area",
    "select_global_allocation",
    "select_proxy_view_candidates",
    "select_seed_candidates",
    "teams_are_disjoint",
    "to_solo_raid_usage_evidence",
]
