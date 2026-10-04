"""Small deterministic experiment used by the repository verification command."""

from __future__ import annotations

from discolab import ArtifactSchema, FieldSchema, MetricSpec, ResourceBudget, experiment


OBSERVATIONS = ArtifactSchema(
    name="observations",
    version=1,
    kind="table",
    fields=(
        FieldSchema("sample", "integer", unit="index", role="index", minimum=0),
        FieldSchema("value", "number", unit="score", role="observation"),
    ),
)
SAMPLE_MEAN = MetricSpec(
    "sample_mean",
    unit="score",
    role="primary",
    minimum=-10,
    maximum=10,
)


@experiment(
    capability="verification",
    hypothesis="A named seeded stream reproduces byte-identical observations.",
    protocol=__file__,
    outputs=(OBSERVATIONS,),
    primary_metric=SAMPLE_MEAN,
)
def deterministic_fixture(run):
    values = run.child_rng("verification-samples").normal(size=16)
    run.consume(len(values))
    run.emit.table(
        "observations",
        [
            {"sample": index, "value": float(value)}
            for index, value in enumerate(values)
        ],
        schema=OBSERVATIONS.id,
    )
    run.metric("sample_mean", float(values.mean()))


def execute(root):
    """Execute the deterministic fixture with its frozen verification budget."""
    return deterministic_fixture.run(
        root,
        parameters={"samples": 16, "stream": "verification-samples"},
        seed=2026,
        budget=ResourceBudget(max_evaluations=16, max_seconds=30),
    )
