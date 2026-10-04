"""Minimal reproducible evidence run using the Python SDK."""

from discolab import ArtifactSchema, FieldSchema, MetricSpec, ResourceBudget, experiment

OBSERVATIONS = ArtifactSchema(
    name="observations",
    version=1,
    kind="table",
    fields=(FieldSchema("value", "number", unit="score", role="observation"),),
)
RUNTIME = MetricSpec("runtime", unit="seconds", role="primary", minimum=0)


@experiment(
    capability="simulation",
    hypothesis="A seeded simulation produces reproducible observations.",
    protocol=__file__,
    outputs=(OBSERVATIONS,),
    primary_metric=RUNTIME,
)
def simulate(run):
    values = run.child_rng("simulation").normal(size=4)
    run.consume(4)
    run.emit.table(
        "observations",
        [{"value": float(value)} for value in values],
        schema=OBSERVATIONS.id,
    )
    run.metric("runtime", run.elapsed_seconds)


if __name__ == "__main__":
    print(simulate.run(
        "study",
        parameters={"samples": 4},
        seed=2026,
        budget=ResourceBudget(max_evaluations=4, max_seconds=30),
    ))
