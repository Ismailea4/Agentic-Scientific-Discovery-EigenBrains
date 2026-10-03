"""Offline exporter for Architecture Baseline v0."""

from __future__ import annotations

import argparse
from pathlib import Path

from .baseline_artifacts import write_prechallenge_baseline_v0
from .cli import _load_runs
from .evaluators import SCORING_V1_HASH
from .metrics import aggregate_architectures
from .templates import architecture_templates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build baseline_v0 artifacts from previously recorded calls; never contacts providers."
    )
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--benchmark-version", required=True)
    parser.add_argument("--benchmark-date", required=True)
    parser.add_argument("--split", required=True, choices=("dev", "tuning", "held_out"))
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--bootstrap-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--lower-percentile", type=float, default=0.1)
    parser.add_argument("--severe-failure-threshold", type=float, required=True)
    parser.add_argument("--failure-threshold", type=float, required=True)
    parser.add_argument("--prior-strength", type=float, required=True)
    parser.add_argument("--maximum-prior-strength", type=float, required=True)
    parser.add_argument("--correlation-penalty", type=float, default=1.0)
    parser.add_argument("--covariance-shrinkage-intensity", type=float, default=0.25)
    args = parser.parse_args()

    runs = _load_runs(args.runs)
    results = aggregate_architectures(
        runs,
        architecture_templates(),
        lower_percentile=args.lower_percentile,
        severe_failure_threshold=args.severe_failure_threshold,
    )
    paths = write_prechallenge_baseline_v0(
        args.benchmark_root,
        runs=runs,
        architecture_results=results,
        experiment_metadata={
            "benchmark_version": args.benchmark_version,
            "benchmark_date": args.benchmark_date,
            "split": args.split,
            "confidence_level": args.confidence_level,
            "bootstrap_resamples": args.bootstrap_resamples,
            "seed": args.seed,
            "severe_failure_threshold": args.severe_failure_threshold,
            "failure_threshold": args.failure_threshold,
            "prior_strength": args.prior_strength,
            "maximum_prior_strength": args.maximum_prior_strength,
            "correlation_penalty": args.correlation_penalty,
            "scoring_config_hash": SCORING_V1_HASH,
            "covariance_shrinkage_intensity": args.covariance_shrinkage_intensity,
        },
    )
    print(f"wrote {len(paths)} scrubbed baseline_v0 artifacts under {args.benchmark_root.resolve()}")


if __name__ == "__main__":
    main()
