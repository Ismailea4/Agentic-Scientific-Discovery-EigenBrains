"""Generate the frozen Baseline-v0 protocol and budget without provider calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..instrumentation.pricing import PricingTable
from .baseline_plan import write_plan_artifacts
from .corpus import build_generic_prior_v0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    pricing = PricingTable.from_checked_json(args.pricing)
    paths = write_plan_artifacts(
        args.benchmark_root,
        cases=build_generic_prior_v0(),
        protocol=protocol,
        pricing=pricing,
    )
    print(f"wrote {len(paths)} offline plan artifacts; provider calls: 0")


if __name__ == "__main__":
    main()
