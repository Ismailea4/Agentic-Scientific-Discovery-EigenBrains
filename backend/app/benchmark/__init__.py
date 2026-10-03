"""Reproducible benchmark and architecture-optimization laboratory."""

from .models import (
    ArchitectureBenchmarkResult,
    ArchitectureTemplate,
    BenchmarkCase,
    BenchmarkRun,
    BenchmarkSplit,
    Difficulty,
    ModelBenchmarkResult,
    RiskLevel,
    SystemOutcome,
)
from .templates import architecture_templates
from .artifacts import SecretScrubber, write_benchmark_artifacts
from .dataset import load_benchmark_cases
from .runner import BenchmarkRunner
from .publish import publish_measured_architectures
from .analysis import aggregate_models
from .cache import ImmutableBenchmarkCache, benchmark_cache_key
from .calibration import abstention_metrics, calibration_metrics
from .controls import BenchmarkLimits, BudgetController, project_full_benchmark
from .key_status import CredentialStatus, KeyStatusRecord
from .baseline_artifacts import write_prechallenge_baseline_v0
from .bounds import (
    ArchitectureBounds,
    estimate_architecture_bounds,
    estimate_task_specific_bounds,
    robust_frontier,
)
from .corpus import CORPUS_VERSION, build_generic_prior_v0
from .distributions import ArchitectureDistribution, summarize_runs
from .downside import DownsideRisk, empirical_downside_risk
from .priors import ArchitecturePrior, construct_architecture_priors

__all__ = [
    "ArchitectureBenchmarkResult",
    "ArchitectureBounds",
    "ArchitectureDistribution",
    "ArchitecturePrior",
    "ArchitectureTemplate",
    "BenchmarkCase",
    "BenchmarkRun",
    "BenchmarkSplit",
    "Difficulty",
    "ModelBenchmarkResult",
    "RiskLevel",
    "SystemOutcome",
    "BenchmarkRunner",
    "BenchmarkLimits",
    "BudgetController",
    "CredentialStatus",
    "CORPUS_VERSION",
    "DownsideRisk",
    "KeyStatusRecord",
    "ImmutableBenchmarkCache",
    "SecretScrubber",
    "architecture_templates",
    "aggregate_models",
    "abstention_metrics",
    "benchmark_cache_key",
    "calibration_metrics",
    "build_generic_prior_v0",
    "construct_architecture_priors",
    "empirical_downside_risk",
    "estimate_architecture_bounds",
    "estimate_task_specific_bounds",
    "load_benchmark_cases",
    "publish_measured_architectures",
    "project_full_benchmark",
    "robust_frontier",
    "summarize_runs",
    "write_benchmark_artifacts",
    "write_prechallenge_baseline_v0",
]
