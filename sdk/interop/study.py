"""Authoritative Python stages of the three-language interoperability demo."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from discolab import ArtifactSchema, FieldSchema, MetricSpec, ResourceBudget, experiment
from discolab.stats import auroc
from discolab.telemetry import population_entropy


PROTOCOL = str(Path(__file__).with_name("PROTOCOL.md"))
TOLERANCE = 1e-12

POPULATION = ArtifactSchema(
    "population",
    1,
    "array",
    dtype="float64",
    ndim=2,
    unit="decision_space",
    role="observation",
)
PREDICTIONS = ArtifactSchema(
    "predictions",
    1,
    "table",
    role="observation",
    fields=(
        FieldSchema("cluster", "string", role="cluster"),
        FieldSchema("label", "boolean", role="label"),
        FieldSchema("score", "number", unit="risk_score", role="score", minimum=0, maximum=1),
    ),
)
REFERENCE = ArtifactSchema("python_reference", 1, "json", role="reference")
INTEROP_REPORT = ArtifactSchema("interop_report", 1, "json", role="analysis")

REFERENCE_ENTROPY = MetricSpec(
    "reference_entropy", "normalized_entropy", role="primary", minimum=0, maximum=1
)
MAX_DIFFERENCE = MetricSpec(
    "max_abs_difference", "absolute_difference", role="primary", minimum=0
)


def prediction_fixture() -> list[dict]:
    """Six paired clusters with deliberately non-perfect discrimination."""
    negatives = (0.10, 0.28, 0.42, 0.35, 0.52, 0.47)
    positives = (0.90, 0.72, 0.58, 0.65, 0.48, 0.61)
    rows: list[dict] = []
    for index, (negative, positive) in enumerate(zip(negatives, positives, strict=True)):
        cluster = f"cluster-{index + 1}"
        rows.extend(
            (
                {"cluster": cluster, "label": False, "score": negative},
                {"cluster": cluster, "label": True, "score": positive},
            )
        )
    return rows


@experiment(
    capability="interop-fixture",
    hypothesis="A shared deterministic artifact can be consumed consistently by three SDK languages.",
    protocol=PROTOCOL,
    outputs=(POPULATION, PREDICTIONS, REFERENCE),
    primary_metric=REFERENCE_ENTROPY,
)
def produce_fixture(run) -> None:
    lower = float(run.params["lower"])
    upper = float(run.params["upper"])
    bins = int(run.params["bins"])
    rows = int(run.params["rows"])
    columns = int(run.params["columns"])
    population = run.child_rng("population").uniform(lower, upper, size=(rows, columns))
    predictions = prediction_fixture()
    labels = np.asarray([row["label"] for row in predictions], dtype=bool)
    scores = np.asarray([row["score"] for row in predictions], dtype=float)
    entropy = float(population_entropy(population, lower, upper, bins))
    reference = {
        "language": "python",
        "entropy": entropy,
        "auroc": float(auroc(scores, labels)),
        "tolerance": TOLERANCE,
        "population": {"rows": rows, "columns": columns, "lower": lower, "upper": upper, "bins": bins},
        "prediction_rows": len(predictions),
    }
    run.consume(rows)
    run.emit.array("population", population, schema=POPULATION.id)
    run.emit.table("predictions", predictions, schema=PREDICTIONS.id)
    run.emit.json("python_reference", reference, schema=REFERENCE.id)
    run.metric("reference_entropy", entropy)


@experiment(
    capability="interop-verification",
    hypothesis="Independent Rust and Julia computations match the authoritative Python references.",
    protocol=PROTOCOL,
    outputs=(INTEROP_REPORT,),
    primary_metric=MAX_DIFFERENCE,
)
def verify_languages(run) -> None:
    reference = json.loads(Path(run.spec.inputs["python_reference"]).read_text(encoding="utf-8"))
    rust = json.loads(Path(run.spec.inputs["rust_entropy"]).read_text(encoding="utf-8"))
    julia = json.loads(Path(run.spec.inputs["julia_statistics"]).read_text(encoding="utf-8"))
    entropy_difference = abs(float(reference["entropy"]) - float(rust["entropy"]))
    auroc_difference = abs(float(reference["auroc"]) - float(julia["auroc"]))
    maximum = max(entropy_difference, auroc_difference)
    tolerance = float(run.params["tolerance"])
    report = {
        "passed": maximum <= tolerance,
        "tolerance": tolerance,
        "shared_protocol_version": "1.0",
        "languages": {
            "python": {"run_id": run.params["python_run_id"], **reference},
            "rust": {"run_id": run.params["rust_run_id"], **rust},
            "julia": {"run_id": run.params["julia_run_id"], **julia},
        },
        "parity": {
            "entropy_rust_vs_python": entropy_difference,
            "auroc_julia_vs_python": auroc_difference,
            "max_abs_difference": maximum,
        },
    }
    run.emit.json("interop_report", report, schema=INTEROP_REPORT.id)
    run.metric("max_abs_difference", maximum)
    if not report["passed"]:
        raise AssertionError(f"cross-language parity exceeded {tolerance}: {report['parity']}")


DEFAULT_PARAMETERS = {"lower": -5.0, "upper": 5.0, "bins": 8, "rows": 32, "columns": 4}
DEFAULT_BUDGET = ResourceBudget(max_evaluations=32, max_seconds=30)
