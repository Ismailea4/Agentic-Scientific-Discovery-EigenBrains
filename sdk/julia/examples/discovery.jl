using Pkg
Pkg.activate(joinpath(@__DIR__, ".."))
using EigenBrainsSDK

client = open_client(joinpath(@__DIR__, "..", "..", "..", "lab_home", "julia-demo"))
try
    initialize!(client)
    experiment = Dict(
        "kind" => "prediction",
        "title" => "Entropy warning signal",
        "rationale" => "Test incremental predictive information.",
        "hypotheses" => ["H1"],
        "landscapes" => ["rastrigin", "ackley"],
        "n_seeds" => 12,
        "feature_sets" => ["fitness", "fitness+entropy"],
        "controllers" => nothing,
    )
    println(propose!(client, experiment))
    println(score!(client))
finally
    close(client)
end

table = likelihood_table(0.5, 60, 0.1, 0.05)
println("EIG bits = ", expected_information_gain(0.5, table))
