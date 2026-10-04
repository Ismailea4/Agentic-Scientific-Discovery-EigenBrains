using Test
using JSON3
using EigenBrainsSDK

fixture_path = joinpath(@__DIR__, "..", "..", "protocol", "v1", "parity-fixtures.json")
fixture = JSON3.read(read(fixture_path, String), Dict{String,Any})

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
