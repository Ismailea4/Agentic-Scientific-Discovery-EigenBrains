using Test
using JSON
using Random
using Statistics
using EigenBrainsSDK

const PROTOCOL = joinpath(@__DIR__, "..", "..", "protocol", "v1")
fixture = JSON.parse(read(joinpath(PROTOCOL, "parity-fixtures.json"), String))
contracts = JSON.parse(read(joinpath(PROTOCOL, "contract-fixtures.json"), String))
schema = JSON.parse(read(joinpath(PROTOCOL, "schema.json"), String))
roundtrip(x) = JSON.parse(JSON.json(x))

@testset "decision-math parity" begin
    d = fixture["decision_math"]
    table = likelihood_table(d["effect_scale"], d["n"], d["sesoi"], d["alpha"])
    for verdict in keys(d["likelihood_table"])
        @test collect(table[verdict]) ≈ collect(d["likelihood_table"][verdict]) atol=1e-10
    end
    @test expected_information_gain(d["prior"], table) ≈ d["expected_information_gain_bits"] atol=1e-10
end

@testset "Wilson parity" begin
    w = fixture["wilson"]
    @test collect(wilson_interval(w["successes"], w["trials"]; z=w["z"])) ≈ w["expected"] atol=1e-10
end

@testset "AUROC parity and clustered variance" begin
    a = fixture["auroc"]
    @test auroc(Float64.(a["scores"]), Bool.(a["labels"])) ≈ a["expected"] atol=1e-12

    # One observation per cluster: Obuchowski reduces to DeLong (brute force here).
    rng = MersenneTwister(7)
    y = rand(rng, Bool, 60)
    s = randn(rng, 60) .+ 0.8 .* y
    pos, neg = s[y], s[.!y]
    psi(x, z) = x > z ? 1.0 : (x == z ? 0.5 : 0.0)
    v10 = [mean(psi(x, z) for z in neg) for x in pos]
    v01 = [mean(psi(x, z) for x in pos) for z in neg]
    delong_var = var(v10) / length(pos) + var(v01) / length(neg)
    single = clustered_auroc(s, y, collect(1:60))
    @test single.estimate ≈ mean(v10) atol=1e-12
    @test single.se^2 ≈ delong_var rtol=1e-10

    # Clustered data: the analytic SE tracks a cluster bootstrap SE.
    clusters = repeat(1:40, inner=25)
    effect = repeat(randn(rng, 40), inner=25)
    labels = rand(rng, length(clusters)) .< 1 ./ (1 .+ exp.(-effect))
    sa = effect .+ 0.5 .* labels .+ randn(rng, length(clusters))
    sb = effect .+ 0.2 .* labels .+ randn(rng, length(clusters))
    paired = paired_clustered_auroc(sa, sb, labels, clusters)
    boot = Float64[]
    groups = [findall(==(c), clusters) for c in 1:40]
    for _ in 1:400
        pick = reduce(vcat, groups[rand(rng, 1:40, 40)])
        push!(boot, auroc(sa[pick], labels[pick]) - auroc(sb[pick], labels[pick]))
    end
    @test 0.75 < paired.se / std(boot) < 1.33
    @test paired.estimate ≈ paired.auroc_a - paired.auroc_b
end

@testset "contract parity with Python" begin
    @test schema["\$defs"]["request"]["properties"]["method"]["enum"] == METHODS
    @test contracts["methods"] == METHODS
    canonical = contracts["canonical_spec"]
    parsed = spec_from_dict(canonical)
    @test roundtrip(spec_dict(parsed)) == canonical
    built = research_spec(
        "optimization",
        "Population entropy adds early-warning information beyond fitness history.",
        "protocols/early-warning-v1.yaml";
        seed=2026,
        parameters=Dict{String,Any}("population" => 50, "landscape" => "rastrigin",
                                    "rates" => [0.5, 1.0, 2.0], "nested" => Dict("horizon" => 10)),
        outputs=[
            table_schema("trajectory", [
                field_schema("generation", "integer"; unit="generations", role="index", minimum=0.0),
                field_schema("best_error", "number"; unit="objective", role="observation", minimum=0.0),
                field_schema("entropy", "number"; unit="normalized_entropy", role="observation",
                             minimum=0.0, maximum=1.0),
                field_schema("recovery", "number"; unit="generations", role="outcome", nullable=true,
                             minimum=0.0, censoring="right"),
                field_schema("landscape", "string"; role="stratum"),
                field_schema("improved", "boolean"; role="label"),
            ]),
            array_schema("populations", "float64"; version=2, ndim=3, unit="decision_space", role="state"),
            json_schema("summary"; role="analysis"),
        ],
        primary_metric=metric_spec("delta_auroc", "auroc"; role="primary", minimum=-1.0, maximum=1.0),
        budget=ResourceBudget(max_evaluations=100000, max_seconds=600.0),
    )
    @test roundtrip(spec_dict(built)) == canonical

    for case in contracts["invalid_specs"]
        spec = roundtrip(canonical)
        node = spec
        path = case["path"]
        key(k) = k isa Integer ? k + 1 : k   # fixture paths are 0-based
        for k in path[1:end-1]
            node = node[key(k)]
        end
        node[key(path[end])] = case["value"]
        rejected = try
            spec_from_dict(spec)
            false
        catch error
            error isa Union{ContractError,ArgumentError,MethodError,KeyError}
        end
        @test rejected
        rejected || @info "accepted invalid case" case["case"]
    end
end

@testset "Python bridge lifecycle" begin
    python_path = normpath(joinpath(@__DIR__, "..", "..", "..", "discolab"))
    python = get(ENV, "PYTHON", "python")
    spec_for(seed) = research_spec(
        "simulation", "The Julia client records validated evidence.", "julia-inline-protocol";
        seed, parameters=Dict{String,Any}("iterations" => 1),
        outputs=[table_schema("observations", [
            field_schema("value", "number"; unit="score", role="observation", minimum=0.0)])],
        primary_metric=metric_spec("runtime", "seconds"; role="primary", minimum=0.0),
        budget=ResourceBudget(max_evaluations=4),
    )
    mktempdir() do lab_root
        withenv("PYTHONPATH" => python_path) do
            client = open_client(lab_root; python, actor="julia-sdk-test")
            try
                initialize!(client)
                proposed = propose!(client, Dict(
                    "kind" => "prediction",
                    "title" => "Julia bridge contract",
                    "rationale" => "Exercise validated lifecycle transitions.",
                    "hypotheses" => ["H1"],
                    "landscapes" => ["rastrigin", "ackley"],
                    "n_seeds" => 4,
                    "feature_sets" => ["fitness", "fitness+entropy"],
                    "controllers" => nothing,
                ))
                score!(client)
                select!(client, proposed["id"], "highest deterministic utility")
                @test state(client)["selected"] == proposed["id"]
                @test !isempty(events(client))
                @test describe(client)["runner_policy"] == "none"

                value, report = with_research_run(client, spec_for(7)) do run_id
                    consume_research_budget!(client, run_id, 1)
                    emit_research_artifact!(client, run_id, "observations", "table",
                                            [Dict("value" => 1.0)], "observations.v1")
                    record_research_metric!(client, run_id, "runtime", 0.01)
                    :done
                end
                @test value == :done && report["valid"] == true
                accepted = report["run_id"]

                @test_throws ErrorException with_research_run(client, spec_for(8)) do run_id
                    consume_research_budget!(client, run_id, 1)
                    error("simulated client failure")
                end
                failed = list_research_runs(client; status="failed")
                @test length(failed) == 1 && failed[1]["seed"] == 8

                interrupted = begin_research_run!(client, spec_for(9))["run_id"]
                consume_research_budget!(client, interrupted, 2)
                checkpoint_research_run!(client, interrupted, Dict("cursor" => 2))
                close(client)  # the first bridge process goes away
                client = open_client(lab_root; python, actor="julia-sdk-test")
                cursor, resumed = with_resumed_research_run(client, interrupted) do run_id, saved
                    emit_research_artifact!(client, run_id, "observations", "table",
                                            [Dict("value" => 2.0)], "observations.v1")
                    record_research_metric!(client, run_id, "runtime", 0.02)
                    saved["cursor"]
                end
                @test cursor == 2 && resumed["status"] == "validated"

                accept_research_run!(client, accepted, "registered checks passed")
                @test reject_research_run!(client, interrupted, "exercise rejection")["status"] ==
                      "rejected_as_evidence"
                caught = try
                    accept_research_run!(client, interrupted, "too late")
                    nothing
                catch error
                    error
                end
                @test caught isa ProtocolError && caught.code == "EvidenceError"
                bundle = export_research_bundle!(client, [accepted, interrupted], "julia-test")
                verified = verify_research_bundle(client, "julia-test")
                @test verified["valid"] == true && verified["content_sha256"] == bundle["content_sha256"]

                caught = try
                    request!(client, "not-a-method")
                    nothing
                catch error
                    error
                end
                @test caught isa ProtocolError
                @test caught.code == "ValueError"
                @test occursin("unknown SDK method", caught.message)
            finally
                close(client)
            end
        end
    end
end
