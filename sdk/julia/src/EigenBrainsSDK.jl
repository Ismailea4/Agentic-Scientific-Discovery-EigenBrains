module EigenBrainsSDK

using JSON3
using Distributions
using FastGaussQuadrature

export Client, open_client, request!, initialize!, state, propose!, score!, select!, run!,
       entropy_bits, outcome_probabilities, likelihood_table, posterior,
       expected_information_gain, wilson_interval

const PROTOCOL_VERSION = "1.0"

mutable struct Client
    io::IO
    next_id::Int
end

"""Start the persistent Python bridge used by the Julia SDK."""
function open_client(root::AbstractString; python::AbstractString="python", actor::AbstractString="julia-sdk")
    cmd = Cmd([python, "-m", "discolab.rpc", "--root", root, "--actor", actor])
    Client(open(cmd, "r+"), 1)
end

function request!(client::Client, method::AbstractString, params=Dict{String,Any}())
    id = client.next_id
    client.next_id += 1
    request = Dict("id" => id, "version" => PROTOCOL_VERSION, "method" => method, "params" => params)
    write(client.io, JSON3.write(request), '\n')
    flush(client.io)
    response = JSON3.read(readline(client.io), Dict{String,Any})
    get(response, "id", nothing) == id || error("EigenBrains response id mismatch")
    if !get(response, "ok", false)
        detail = get(response, "error", Dict{String,Any}())
        error("EigenBrains protocol error: $(get(detail, "message", "unknown error"))")
    end
    get(response, "result", nothing)
end

initialize!(client::Client) = request!(client, "initialize")
state(client::Client) = request!(client, "state")
propose!(client::Client, experiment) = request!(client, "propose", Dict("experiment" => experiment))
score!(client::Client) = request!(client, "score")
select!(client::Client, id::AbstractString, why::AbstractString) =
    request!(client, "select", Dict("experiment_id" => id, "justification" => why))
run!(client::Client; confirm_heldout::Bool=false) =
    request!(client, "run", Dict("confirm_heldout" => confirm_heldout))

Base.close(client::Client) = close(client.io)

"""Binary entropy in bits."""
function entropy_bits(q::Real)
    0.0 <= q <= 1.0 || throw(DomainError(q, "probability must be in [0, 1]"))
    (q == 0.0 || q == 1.0) && return 0.0
    -q * log2(q) - (1 - q) * log2(1 - q)
end

function outcome_probabilities(effect::Real, n::Integer, sesoi::Real, alpha::Real)
    n > 0 || throw(DomainError(n, "n must be positive"))
    0.0 < alpha < 1.0 || throw(DomainError(alpha, "alpha must be in (0, 1)"))
    normal = Normal()
    z = quantile(normal, 1 - alpha / 2)
    rootn = sqrt(n)
    supported = cdf(normal, effect * rootn - z)
    refuted = cdf(normal, (sesoi - effect) * rootn - z)
    probabilities = Dict(
        "supported" => max(supported, 1e-6),
        "refuted" => max(refuted, 1e-6),
        "inconclusive" => max(1 - supported - refuted, 1e-6),
    )
    total = sum(values(probabilities))
    Dict(key => value / total for (key, value) in probabilities)
end

"""Composite-H1 verdict likelihoods matching the prereg-v3 Python planner."""
function likelihood_table(effect_scale::Real, n::Integer, sesoi::Real, alpha::Real)
    nodes, weights = gausslegendre(40)
    us = (nodes .+ 1) ./ 2
    ws = weights ./ 2
    normal = Normal()
    h1 = Dict(verdict => 0.0 for verdict in ("supported", "inconclusive", "refuted"))
    for (u, weight) in zip(us, ws)
        effect = sesoi + effect_scale * quantile(normal, 0.5 + 0.5u)
        probabilities = outcome_probabilities(effect, n, sesoi, alpha)
        for verdict in keys(h1)
            h1[verdict] += weight * probabilities[verdict]
        end
    end
    h0 = outcome_probabilities(0.0, n, sesoi, alpha)
    Dict(verdict => (h1[verdict], h0[verdict]) for verdict in keys(h1))
end

function posterior(prior::Real, verdict::AbstractString, table)
    0.0 <= prior <= 1.0 || throw(DomainError(prior, "prior must be in [0, 1]"))
    l1, l0 = table[verdict]
    prior * l1 / (prior * l1 + (1 - prior) * l0)
end

function expected_information_gain(prior::Real, table)
    remaining = 0.0
    for verdict in ("supported", "inconclusive", "refuted")
        l1, l0 = table[verdict]
        probability = prior * l1 + (1 - prior) * l0
        remaining += probability * entropy_bits(posterior(prior, verdict, table))
    end
    entropy_bits(prior) - remaining
end

"""Wilson score interval; returns `(estimate, low, high)`."""
function wilson_interval(successes::Integer, trials::Integer; z::Real=1.959963984540054)
    trials > 0 || throw(DomainError(trials, "trials must be positive"))
    0 <= successes <= trials || throw(DomainError(successes, "successes must be in [0, trials]"))
    p = successes / trials
    z2 = z^2
    center = (p + z2 / (2trials)) / (1 + z2 / trials)
    half = z * sqrt(p * (1 - p) / trials + z2 / (4trials^2)) / (1 + z2 / trials)
    (p, max(0.0, center - half), min(1.0, center + half))
end

end
