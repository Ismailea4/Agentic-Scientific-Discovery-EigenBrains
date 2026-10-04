using EigenBrainsSDK

root = isempty(ARGS) ? "study" : ARGS[1]
client = open_client(root; python=get(ENV, "PYTHON", "python"), actor="julia-example")

metric = MetricSpec(name="runtime", unit="seconds", role="primary", minimum=0.0)
spec = ResearchExperimentSpec(
    capability="simulation",
    hypothesis="The Julia client records validated evidence.",
    protocol="protocols/simulation-v1.md",
    parameters=Dict{String,Any}("samples" => 2),
    seed=2026,
    outputs=[ArtifactSchema(
        name="observations",
        kind="table",
        fields=[FieldSchema(
            name="value", dtype="number", unit="score", role="observation",
        )],
    )],
    primary_metric=metric,
    budget=ResourceBudget(max_evaluations=2, max_seconds=30.0),
)

try
    opened = begin_research_run!(client, spec)
    run_id = opened["run_id"]
    consume_research_budget!(client, run_id, 2)
    emit_research_artifact!(
        client, run_id, "observations", "table",
        [Dict("value" => 0.25), Dict("value" => 0.75)], "observations.v1",
    )
    record_research_metric!(client, run_id, "runtime", 0.01)
    println(finalize_research_run!(client, run_id))
finally
    close(client)
end
