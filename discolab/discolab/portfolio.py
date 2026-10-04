"""Failure dependence between mutation controllers, using the EigenBrains
econometrics layer (backend/app/optimization/covariance.py) directly.

Question: do two interventions fail on the same landscape shifts? High overlap
means one adds no diversification beyond the other (e.g. a predictive
controller that behaves like a fixed rate); low overlap means they are
complementary and a combined policy is worth testing.

Two levels, kept separate on purpose:
- shift level (descriptive): every post-shift epoch is a case; error =
  recovery time / horizon (1.0 = not recovered). Shifts within a run are not
  independent, so no intervals are reported at this level.
- run level (inferential): every (landscape, seed) run is a case; error =
  fraction of the run's shifts not recovered; failure = majority not
  recovered. Paired case-bootstrap intervals come from the EigenBrains
  bootstrap, which is valid here because runs are the independent units.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT.parent / "backend"
SHRINKAGE_INTENSITY = 0.25  # frozen EigenBrains baseline value
RUN_FAILURE_THRESHOLD = 0.6  # >= 3 of 5 shifts not recovered


def _eigenbrains():
    if not (BACKEND / "app" / "optimization" / "covariance.py").exists():
        raise RuntimeError("EigenBrains backend not found next to discolab; it provides the covariance analysis")
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.optimization import covariance  # noqa: PLC0415  (EigenBrains module)

    return covariance


def load_outcomes(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def error_vectors(outcomes: list[dict], horizon: int, level: str) -> dict[str, dict[str, float]]:
    vec: dict[str, dict[str, float]] = {}
    for o in outcomes:
        unit = f"{o['landscape']}|{o['seed']}"
        if level == "shift":
            for k, t in enumerate(o["recovery_gens"], start=1):
                vec.setdefault(o["controller"], {})[f"{unit}|shift{k}"] = min(t, horizon) / horizon
        else:
            vec.setdefault(o["controller"], {})[unit] = 1.0 - float(o["recovery_rate"])
    return vec


def analyze(outcomes_path: Path, horizon: int = 60, correlation_penalty: float = 0.5,
            resamples: int = 2000) -> dict:
    cov = _eigenbrains()
    outcomes = load_outcomes(outcomes_path)
    shift = cov.analyze_error_vectors(error_vectors(outcomes, horizon, "shift"), failure_threshold=1.0)
    run_vec = error_vectors(outcomes, horizon, "run")
    run = cov.analyze_error_vectors(run_vec, failure_threshold=RUN_FAILURE_THRESHOLD)
    shrunk = cov.diagonal_shrinkage_covariance(run, intensity=SHRINKAGE_INTENSITY)
    boot = cov.bootstrap_pairwise_metrics(run_vec, failure_threshold=RUN_FAILURE_THRESHOLD, resamples=resamples)
    quality = {c: 1.0 - sum(v.values()) / len(v) for c, v in run_vec.items()}  # mean run recovery rate
    pair = cov.select_complementary_pair(run, quality, correlation_penalty=correlation_penalty)
    return {
        "source": str(outcomes_path.as_posix()),
        "controllers": list(run.labels),
        "n_runs": len(run.case_ids),
        "n_shifts": len(shift.case_ids),
        "shift_level_descriptive": [r for r in shift.to_rows() if r["left"] < r["right"]],
        "run_level": [r for r in run.to_rows() if r["left"] < r["right"]],
        "run_level_bootstrap": [b.to_dict() for b in boot],
        "run_level_shrunk_correlation": {"intensity": SHRINKAGE_INTENSITY, "labels": list(shrunk.labels),
                                         "correlation": [list(r) for r in shrunk.correlations]},
        "mean_run_recovery": quality,
        "complementary_pair": {"pair": list(pair), "correlation_penalty": correlation_penalty,
                               "rule": "EigenBrains select_complementary_pair on run-level recovery and correlation"},
    }


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(json.dumps(analyze(Path(arg)), indent=2, default=str))
