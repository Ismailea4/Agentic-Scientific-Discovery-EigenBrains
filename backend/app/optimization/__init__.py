"""Deterministic architecture comparison utilities.

These functions compare numbers the caller supplies. They do not contain
benchmark results, challenge weights, or covariance estimates.
"""

from .covariance import ErrorCovariance, ErrorCovarianceMatrix
from .models import (
    AgentMetrics,
    AgentProfile,
    ArchitectureCandidate,
    ArchitectureMetrics,
    OptimizationConstraints,
    OptimizationResult,
    OptimizationWeights,
)
from .pareto import ParetoResult, pareto_frontier
from .selection import select_architecture, select_best
from .tail_risk import TailRiskEstimate
from .utility import utility, weighted_utility
from .portfolio import ComputationalAllocation, analyze_computational_allocation

__all__ = [
    "AgentMetrics",
    "AgentProfile",
    "ArchitectureCandidate",
    "ArchitectureMetrics",
    "ComputationalAllocation",
    "ErrorCovariance",
    "ErrorCovarianceMatrix",
    "OptimizationConstraints",
    "OptimizationResult",
    "OptimizationWeights",
    "ParetoResult",
    "TailRiskEstimate",
    "pareto_frontier",
    "analyze_computational_allocation",
    "select_architecture",
    "select_best",
    "utility",
    "weighted_utility",
]
