# Independently recompute Python-produced AUROC evidence and record the result
# through the same protocol-v1 evidence store.

using EigenBrainsSDK
using JSON

length(ARGS) == 4 || error(
    "usage: interop_audit.jl EVIDENCE_ROOT PREDICTIONS_JSONL PYTHON_REFERENCE_JSON PROTOCOL"
)
root, predictions_path, reference_path, protocol_path = ARGS

rows = [JSON.parse(line) for line in eachline(predictions_path) if !isempty(strip(line))]
scores = Float64[row["score"] for row in rows]
labels = Bool[row["label"] for row in rows]
clusters = String[row["cluster"] for row in rows]
reference = JSON.parsefile(reference_path)

started = time_ns()
estimate = auroc(scores, labels)
clustered = clustered_auroc(scores, labels, clusters)
compute_seconds = (time_ns() - started) / 1e9
difference = abs(estimate - Float64(reference["auroc"]))
output = Dict{String,Any}(
    "language" => "julia",
    "implementation" => "EigenBrainsSDK.auroc + clustered_auroc",
    "auroc" => estimate,
    "python_reference" => Float64(reference["auroc"]),
    "abs_difference" => difference,
    "native_compute_seconds" => compute_seconds,
    "observations" => length(rows),
    "clusters" => length(unique(clusters)),
    "clustered_interval" => Dict(
        "estimate" => clustered.estimate,
        "se" => clustered.se,
        "low" => clustered.low,
        "high" => clustered.high,
        "clusters" => clustered.clusters,
    ),
)

spec = research_spec(
    "statistical-audit",
    "Julia independently reproduces AUROC and estimates clustered uncertainty.",
    protocol_path;
    seed=2026,
    inputs=Dict("predictions" => predictions_path, "python_reference" => reference_path),
    outputs=[json_schema("julia_statistics"; role="analysis")],
    primary_metric=metric_spec("native_compute_seconds", "seconds"; role="primary", minimum=0.0),
    budget=ResourceBudget(max_evaluations=1, max_seconds=30.0),
)

client = open_client(root; python=get(ENV, "PYTHON", "python"), actor="julia-interop-auditor")
try
    _, report = with_research_run(client, spec) do run_id
        consume_research_budget!(client, run_id, 1)
        emit_research_artifact!(
            client, run_id, "julia_statistics", "json", output, "julia_statistics.v1"
        )
        record_research_metric!(client, run_id, "native_compute_seconds", compute_seconds)
    end
    println(JSON.json(Dict(
        "language" => "julia",
        "run_id" => report["run_id"],
        "auroc" => estimate,
        "abs_difference" => difference,
        "native_compute_seconds" => compute_seconds,
    )))
finally
    close(client)
end
