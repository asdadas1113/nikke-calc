"""Roster optimizer prototype built around the Moris simulator evaluator."""

from .account import (
    AccountSnapshot,
    AccountSyncAdapter,
    FieldProvenance,
    ProvenanceStatus,
    normalize_account_sync,
)
from .account_bundle import AuditedAccountSnapshot, normalize_account_bundle
from .anytime import AnytimeSearchResult, AnytimeStageMetrics, run_anytime_search_round
from .blablalink import normalize_blablalink_worker_payload, select_blablalink_area
from .budget import BudgetedEvaluator, SearchBudget, SearchBudgetExhausted
from .candidates import CandidateTeam
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
from .evaluator import (
    CacheIdentity,
    Evaluation,
    EvaluationTimings,
    EvaluatorStats,
    MorisEvaluator,
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
from .meta_usage import (
    CharacterUsageWindow,
    EnikkSeasonUsageSnapshot,
    ExternalNameMapping,
    SeasonUsageObservation,
    aggregate_character_window,
    build_external_name_mapping,
    summarize_enikk_rankings,
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
from .refinement import OneSwapNeighbor, generate_one_swap_neighbors
from .seeds import (
    CoreSeed,
    ExactCompSeed,
    SeedCandidate,
    SeedSelection,
    select_seed_candidates,
)
from .synergy import PairSynergyObservation, PairSynergyProbe, measure_pair_probes
from .validation import ValidationMetrics, enumerate_legal_teams, run_exhaustive_validation

__all__ = [
    "AccountSnapshot",
    "AccountSyncAdapter",
    "Allocation",
    "AllocationRefinementResult",
    "AnytimeSearchResult",
    "AnytimeStageMetrics",
    "AuditedAccountSnapshot",
    "BudgetedEvaluator",
    "BurstMetadata",
    "BurstStructureReport",
    "BurstStructureValidator",
    "CacheIdentity",
    "CandidateMarginalPlan",
    "CandidateMarginalPlanEntry",
    "CandidateTeam",
    "CharacterUsageWindow",
    "ColdDecision",
    "ColdPoolPartition",
    "ColdRestorationResult",
    "ConstraintSet",
    "CoreSeed",
    "EnikkSeasonUsageSnapshot",
    "Evaluation",
    "EvaluationTimings",
    "EvaluatorStats",
    "ExactCompSeed",
    "ExternalNameMapping",
    "FieldProvenance",
    "MarginalMeasurement",
    "MarginalObservation",
    "MarginalValue",
    "MorisEvaluator",
    "OneSwapNeighbor",
    "OverloadKnowledge",
    "OverloadPieceEvidence",
    "PairSynergyObservation",
    "PairSynergyProbe",
    "PipelineStageMetrics",
    "ProvenanceStatus",
    "ProxyView",
    "ProxyViewCandidate",
    "ProxyViewHit",
    "RestorationStep",
    "SearchBudget",
    "SearchBudgetExhausted",
    "SeasonUsageObservation",
    "SeedCandidate",
    "SeedSelection",
    "SoloRaidUsageEvidence",
    "StructuralDemand",
    "StructuralFeasibility",
    "TeamRequirement",
    "UsageClass",
    "ValidationMetrics",
    "aggregate_character_window",
    "build_burst_role_map",
    "build_external_name_mapping",
    "build_planned_marginal_prefix_views",
    "check_structural_feasibility",
    "derive_overload_piece_evidence",
    "enumerate_legal_teams",
    "evaluate_allocation_with_one_swap_refinement",
    "generate_one_swap_neighbors",
    "measure_marginals",
    "measure_marginals_with_candidates",
    "measure_pair_probes",
    "measure_planned_marginals_with_candidates",
    "normalize_account_bundle",
    "normalize_account_sync",
    "normalize_blablalink_worker_payload",
    "partition_meta_guided_roster",
    "plan_candidate_specific_marginals",
    "reorder_candidate_marginal_plan",
    "restore_cold_until_feasible",
    "run_anytime_search_round",
    "run_exhaustive_validation",
    "select_blablalink_area",
    "select_global_allocation",
    "select_proxy_view_candidates",
    "select_seed_candidates",
    "summarize_enikk_rankings",
    "teams_are_disjoint",
]
