"""Weighted utility.

The form is `w.quality_weight*quality - w.lambda_risk*risk - w.eta_cost*cost - w.rho_latency*latency`.
Weights come from the caller. This module has no default challenge calibration.
"""

from __future__ import annotations

from .models import ArchitectureMetrics, OptimizationWeights


def weighted_utility(metrics: ArchitectureMetrics, weights: OptimizationWeights) -> float:
    weights.validate()
    return (
        weights.quality_weight * metrics.quality
        - weights.lambda_risk * metrics.risk
        - weights.eta_cost * metrics.cost
        - weights.rho_latency * metrics.latency
    )


# Backwards-compatible alias for the pre-rename name.
utility = weighted_utility
