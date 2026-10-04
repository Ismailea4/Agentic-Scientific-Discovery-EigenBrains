using Test
using JSON
using EigenBrainsSDK

fixture_path = joinpath(@__DIR__, "..", "..", "protocol", "v1", "parity-fixtures.json")
fixture = JSON.parse(read(fixture_path, String))

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

@testset "Python bridge lifecycle" begin
    python_path = normpath(joinpath(@__DIR__, "..", "..", "..", "discolab"))
    mktempdir() do lab_root
        withenv("PYTHONPATH" => python_path) do
            client = open_client(
                lab_root;
                python=get(ENV, "PYTHON", "python"),
                actor="julia-sdk-test",
            )
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
