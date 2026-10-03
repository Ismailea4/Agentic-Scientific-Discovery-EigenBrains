"""Generate the empirical pilot report from recorded calls only."""

from __future__ import annotations

import argparse
from pathlib import Path

from .cli import _load_runs
from .pilot_report import build_pilot_report, write_pilot_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline report for an already-recorded pilot.")
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--bootstrap-resamples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--severe-failure-threshold", type=float, default=0.2)
    args = parser.parse_args()
    report = build_pilot_report(
        _load_runs(args.runs),
        confidence_level=args.confidence_level,
        resamples=args.bootstrap_resamples,
        seed=args.seed,
        severe_failure_threshold=args.severe_failure_threshold,
    )
    paths = write_pilot_report(args.benchmark_root, report)
    print(f"wrote {len(paths)} scrubbed pilot artifacts")


if __name__ == "__main__":
    main()
