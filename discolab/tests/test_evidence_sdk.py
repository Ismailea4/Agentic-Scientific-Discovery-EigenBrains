import json
from pathlib import Path

import numpy as np
import pytest

from discolab import (
    ArtifactSchema,
    BudgetExceeded,
    EvidenceStore,
    ExperimentSpecV2,
    FieldSchema,
    MetricSpec,
    ResourceBudget,
    ValidationError,
    experiment,
)


TRAJECTORY = ArtifactSchema(
    name="trajectory",
    version=1,
    kind="table",
    fields=(
        FieldSchema("evaluation", "integer", unit="count", role="index", minimum=0),
        FieldSchema("loss", "number", unit="objective", role="observation", minimum=0),
    ),
)
RECOVERY = MetricSpec(
    "recovery_time", unit="evaluations", role="primary", minimum=0, censoring="right"
)


@experiment(
    capability="optimization",
    hypothesis="Deterministic search reaches the target.",
    protocol=__file__,
    outputs=(TRAJECTORY,),
    primary_metric=RECOVERY,
)
def deterministic_experiment(context):
    noise = context.child_rng("trajectory").uniform(0, 1, 3)
    context.consume(3)
    context.emit.table(
        "trajectory",
        [{"evaluation": index, "loss": float(value)} for index, value in enumerate(noise)],
        schema=TRAJECTORY.id,
    )
    context.metric("recovery_time", 3)


def _manual_spec(seed=7, max_evaluations=10):
    return ExperimentSpecV2(
        capability="optimization",
        hypothesis="A seeded algorithm emits auditable evidence.",
        protocol=__file__,
        parameters={"population": 8},
        seed=seed,
        outputs=(TRAJECTORY,),
        primary_metric=RECOVERY,
        budget=ResourceBudget(max_evaluations=max_evaluations),
    )


def test_decorated_run_is_reproducible_and_has_provenance(tmp_path):
    first = deterministic_experiment.run(tmp_path, parameters={}, seed=42)
    replay = EvidenceStore(tmp_path).reproduce(first["run_id"])
    first_snapshot = EvidenceStore(tmp_path).inspect(first["run_id"])
    replay_snapshot = EvidenceStore(tmp_path).inspect(replay["run_id"])

    assert first["status"] == "validated"
    assert replay_snapshot["spec"]["reproduction_of"] == first["run_id"]
    assert first_snapshot["metrics"] == replay_snapshot["metrics"]
    first_rows = Path(tmp_path, "research-runs", first["run_id"], "artifacts", "raw", "trajectory.jsonl")
    replay_rows = Path(tmp_path, "research-runs", replay["run_id"], "artifacts", "raw", "trajectory.jsonl")
    assert first_rows.read_bytes() == replay_rows.read_bytes()
    assert first_snapshot["provenance"]["protocol"]["sha256"]
    assert first_snapshot["provenance"]["runner"]["sha256"]


def test_semantic_validation_budget_and_tamper_detection(tmp_path):
    context = EvidenceStore(tmp_path).begin(_manual_spec(max_evaluations=2))
    with pytest.raises(BudgetExceeded):
        context.consume(3)
    context.fail(BudgetExceeded("test budget"))
    assert EvidenceStore(tmp_path).inspect(context.run_id)["status"] == "failed"

    mismatched = EvidenceStore(tmp_path).begin(_manual_spec())
    altered_schema = ArtifactSchema(
        name="trajectory", version=1, kind="table",
        fields=TRAJECTORY.fields, allow_extra_fields=True,
    )
    with pytest.raises(ValidationError, match="differs from its declaration"):
        mismatched.emit.table(
            "trajectory", [{"evaluation": 0, "loss": 1.0}], schema=altered_schema,
        )
    mismatched.fail(ValidationError("test mismatch"))

    good = EvidenceStore(tmp_path).begin(_manual_spec())
    good.emit.table("trajectory", [{"evaluation": 0, "loss": 1.0}], schema=TRAJECTORY.id)
    good.metric("recovery_time", 1)
    report = good.finalize()
    artifact = Path(tmp_path, "research-runs", report["run_id"], "artifacts", "raw", "trajectory.jsonl")
    artifact.write_text(json.dumps({"evaluation": 0, "loss": 2.0}) + "\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="hash mismatch"):
        EvidenceStore(tmp_path).validate(report["run_id"])


def test_compare_and_accept_lifecycle(tmp_path):
    run_ids = []
    for seed, value in ((1, 5.0), (2, 3.0)):
        context = EvidenceStore(tmp_path).begin(_manual_spec(seed=seed))
        context.emit.table("trajectory", [{"evaluation": 0, "loss": value}], schema=TRAJECTORY.id)
        context.metric("recovery_time", value)
        run_ids.append(context.finalize()["run_id"])
    comparison = EvidenceStore(tmp_path).compare(*run_ids)
    assert comparison["metrics"]["recovery_time"]["delta_right_minus_left"] == -2.0
    accepted = EvidenceStore(tmp_path).accept(run_ids[0], "passed the registered checks")
    assert accepted["status"] == "accepted_as_evidence"


def test_discovery_lab_generic_rpc_surface(tmp_path):
    from discolab import DiscoveryLab

    client = DiscoveryLab(tmp_path)
    opened = client.begin_research_run(_manual_spec().to_dict())
    run_id = opened["run_id"]
    client.consume_research_budget(run_id, 1)
    client.emit_research_artifact(
        run_id,
        name="trajectory",
        kind="table",
        value=[{"evaluation": 0, "loss": 1.0}],
        schema=TRAJECTORY.id,
    )
    client.record_research_metric(run_id, "recovery_time", 1)
    assert client.finalize_research_run(run_id)["valid"] is True
