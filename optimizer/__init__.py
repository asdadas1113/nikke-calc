"""Roster optimizer prototype built around the Moris simulator evaluator."""

from .account import (
    AccountSnapshot,
    AccountSyncAdapter,
    FieldProvenance,
    ProvenanceStatus,
    normalize_account_sync,
)
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
from .refinement import OneSwapNeighbor, generate_one_swap_neighbors
from .synergy import PairSynergyObservation, PairSynergyProbe, measure_pair_probes
from .validation import ValidationMetrics, enumerate_legal_teams, run_exhaustive_validation

__all__ = [
    "AccountSnapshot",
    "AccountSyncAdapter",
    "Allocation",
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
    "MorisEvaluator",
    "OneSwapNeighbor",
    "PairSynergyObservation",
    "PairSynergyProbe",
    "ProvenanceStatus",
    "ValidationMetrics",
    "enumerate_legal_teams",
    "generate_one_swap_neighbors",
    "measure_pair_probes",
    "normalize_account_sync",
    "run_exhaustive_validation",
    "select_global_allocation",
    "teams_are_disjoint",
]
