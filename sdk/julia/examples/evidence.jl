# Record one validated evidence run from Julia:
#   julia --project=sdk/julia sdk/julia/examples/evidence.jl <lab root>
# The Python sidecar (`discolab`) must be importable by the selected Python.
using EigenBrainsSDK

root = isempty(ARGS) ? "study" : ARGS[1]
client = open_client(root; python=get(ENV, "PYTHON", "python"), actor="julia-example")

spec = research_spec(
    "simulation", "The Julia client records validated evidence.", "protocols/simulation-v1.md";
    seed=2026,
    parameters=Dict{String,Any}("samples" => 2),
    outputs=[table_schema("observations", [field_schema("value", "number"; unit="score", role="observation")])],
    primary_metric=metric_spec("runtime", "seconds"; role="primary", minimum=0.0),
    budget=ResourceBudget(max_evaluations=2, max_seconds=30.0),
)

try
    _, report = with_research_run(client, spec) do run_id
        consume_research_budget!(client, run_id, 2)
        emit_research_artifact!(client, run_id, "observations", "table",
                                [Dict("value" => 0.25), Dict("value" => 0.75)], "observations.v1")
        record_research_metric!(client, run_id, "runtime", 0.01)
    end
    println(report)
finally
    close(client)
end
