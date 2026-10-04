# Independent statistics on the hashed predictions artifact of the confirmatory run.
#
#   julia --project=../../sdk/julia julia/analysis.jl <store> <predictions.jsonl> [protocol] [seed]
#
# Recomputes the AUROC of every score column (checked against Python by the
# cross-language run) and the EW1 contrast with the analytic clustered
# variance of Obuchowski (1997), clusters = (landscape, seed). The result is
# recorded as its own evidence run in the same store via the Python sidecar.
using JSON
using EigenBrainsSDK

const SCORES = ["fitness", "fitness+entropy", "fitness+dispersion", "fitness+dispersion+entropy",
                "entropy_only", "progress_rate_rule", "diversity_rule"]
column(name) = "score_" * replace(name, "+" => "_")

root, predictions = ARGS[1], ARGS[2]
protocol = length(ARGS) >= 3 ? ARGS[3] : "protocol.yaml"
seed = length(ARGS) >= 4 ? parse(Int, ARGS[4]) : 0

rows = [JSON.parse(line) for line in eachline(predictions) if !isempty(strip(line))]
labels = Bool[r["stagnates"] for r in rows]
clusters = String[r["cluster"] for r in rows]
scores = Dict(name => Float64[r[column(name)] for r in rows] for name in SCORES)

spec = research_spec(
    "statistics-audit",
    "Julia independently recomputes the confirmatory AUROCs and gives an analytic clustered interval for EW1.",
    protocol;
    seed,
    parameters=Dict{String,Any}("method" => "Obuchowski 1997 clustered nonparametric AUROC variance",
                                "cluster" => "(landscape, seed)", "level" => 0.95),
    inputs=Dict("predictions" => predictions),
    outputs=[
        table_schema("julia_auroc", [field_schema("score", "string"; role="index"),
                                     field_schema("auroc", "number"; unit="auroc", role="estimate",
                                                  minimum=0.0, maximum=1.0)]; role="analysis"),
        json_schema("julia_obuchowski"; role="analysis"),
    ],
    primary_metric=metric_spec("julia_delta_auroc", "auroc"; role="primary", minimum=-1.0, maximum=1.0),
)

client = open_client(root; python=get(ENV, "PYTHON", "python"), actor="julia-statistics-audit")
try
    _, report = with_research_run(client, spec) do run_id
        table = [Dict("score" => name, "auroc" => auroc(scores[name], labels)) for name in SCORES]
        emit_research_artifact!(client, run_id, "julia_auroc", "table", table, "julia_auroc.v1")
        ew1 = paired_clustered_auroc(scores["fitness+entropy"], scores["fitness"], labels, clusters)
        secondary = Dict(
            "EW2" => paired_clustered_auroc(scores["fitness+dispersion+entropy"], scores["fitness+dispersion"],
                                            labels, clusters),
            "EW3" => paired_clustered_auroc(scores["fitness+dispersion"], scores["fitness"], labels, clusters),
            "EW4" => paired_clustered_auroc(scores["entropy_only"], scores["fitness"], labels, clusters),
        )
        asdict(t) = Dict(String(k) => v for (k, v) in pairs(t))
        emit_research_artifact!(client, run_id, "julia_obuchowski", "json", Dict(
            "EW1" => asdict(ew1), "secondary" => Dict(k => asdict(v) for (k, v) in secondary),
            "observations" => length(labels), "clusters" => ew1.clusters,
            "reference" => "Obuchowski NA (1997) Biometrics 53:567-578; DeLong et al. (1988) Biometrics 44:837-845",
        ), "julia_obuchowski.v1")
        record_research_metric!(client, run_id, "julia_delta_auroc", ew1.estimate)
    end
    println(JSON.json(Dict("run_id" => report["run_id"], "status" => report["status"])))
finally
    close(client)
end
