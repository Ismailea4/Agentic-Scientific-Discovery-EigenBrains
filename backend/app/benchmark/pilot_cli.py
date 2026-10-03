"""Plan or execute the bounded single-model Baseline v0 pilot."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ..instrumentation.pricing import PricingTable
from .controls import BenchmarkLimits, authorize_projection
from .corpus import build_generic_prior_v0
from .pilot import (
    load_shortlist,
    pilot_projection,
    run_single_model_pilot,
    select_pilot_cases,
    write_pilot_runs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan-first provider pilot; calls require --execute and limits.")
    parser.add_argument("--shortlist", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-task", type=int, default=2)
    parser.add_argument("--input-token-cap", type=int, default=1024)
    parser.add_argument("--output-token-cap", type=int, default=256)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    cases = select_pilot_cases(build_generic_prior_v0(), per_task=args.per_task)
    specs = load_shortlist(args.shortlist)
    pricing = PricingTable.from_checked_json(args.pricing)
    projection = pilot_projection(
        specs,
        cases,
        pricing,
        input_token_cap=args.input_token_cap,
        output_token_cap=args.output_token_cap,
    )
    print(json.dumps({
        "mode": "execute" if args.execute else "plan_only",
        "cases": len(cases),
        "models": len(specs),
        "total_calls": sum(item.projected_calls for item in projection),
        "maximum_projected_cost_usd": sum(float(item.projected_cost_usd or 0) for item in projection),
        "models_projection": [item.to_dict() for item in projection],
    }, indent=2))
    if not args.execute:
        return
    limits = BenchmarkLimits.from_environment()
    authorize_projection(projection, limits)
    runs = asyncio.run(
        run_single_model_pilot(
            cases,
            specs,
            pricing,
            limits,
            output_token_cap=args.output_token_cap,
            input_token_cap=args.input_token_cap,
            seed=args.seed,
        )
    )
    write_pilot_runs(args.output, runs)
    print(json.dumps({"recorded_runs": len(runs), "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
