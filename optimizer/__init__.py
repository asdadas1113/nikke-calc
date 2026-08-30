"""Roster optimizer prototype built around the Moris simulator evaluator."""

from .account import (
    AccountSnapshot,
    AccountSyncAdapter,
    FieldProvenance,
    ProvenanceStatus,
    normalize_account_sync,
)
from .account_bundle import AuditedAccountSnapshot, normalize_account_bundle
from .blablalink import normalize_blablalink_worker_payload, select_blablalink_area
from .candidates import CandidateTeam
from .constraints import (
    BurstMetadata,
    BurstStructureReport,
    BurstStructureValidator,
    ConstraintSet,
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
from .marginal import MarginalMeasurement, measure_marginals_with_candidates
from .pipeline import (
    AllocationRefinementResult,
    PipelineStageMetrics,
    evaluate_allocation_with_one_swap_refinement,
)
from .refinement import OneSwapNeighbor, generate_one_swap_neighbors
from .synergy import PairSynergyObservation, PairSynergyProbe, measure_pair_probes
from .validation import ValidationMetrics, enumerate_legal_teams, run_exhaustive_validation

__all__ = [
    "AccountSnapshot",
    "AccountSyncAdapter",
    "Allocation",
    "AllocationRefinementResult",
    "AuditedAccountSnapshot",
    "BurstMetadata",
    "BurstStructureReport",
    "BurstStructureValidator",
    "CacheIdentity",
    "CandidateTeam",
    "ConstraintSet",
    "Evaluation",
    "EvaluationTimings",
    "EvaluatorStats",
    "FieldProvenance",
    "MarginalMeasurement",
    "MorisEvaluator",
    "OneSwapNeighbor",
    "PairSynergyObservation",
    "PairSynergyProbe",
    "PipelineStageMetrics",
    "ProvenanceStatus",
    "ValidationMetrics",
    "enumerate_legal_teams",
    "evaluate_allocation_with_one_swap_refinement",
    "generate_one_swap_neighbors",
    "measure_marginals_with_candidates",
    "measure_pair_probes",
    "normalize_account_bundle",
    "normalize_account_sync",
    "normalize_blablalink_worker_payload",
    "run_exhaustive_validation",
    "select_blablalink_area",
    "select_global_allocation",
    "teams_are_disjoint",
]
