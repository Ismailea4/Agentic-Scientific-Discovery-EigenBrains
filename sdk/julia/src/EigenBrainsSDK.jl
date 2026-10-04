module EigenBrainsSDK

using JSON
using Distributions
using FastGaussQuadrature

export Client, ProtocolError, open_client, request!, initialize!, state, events,
       propose!, score!, select!, run!, abort!, result, analyze!, decide!,
       register_hypothesis!,
       ResourceBudget, FieldSchema, ArtifactSchema, MetricSpec, ResearchExperimentSpec,
       begin_research_run!, emit_research_artifact!, record_research_metric!,
       consume_research_budget!, finalize_research_run!, inspect_research_run,
       validate_research_run, compare_research_runs, accept_research_run!,
       reproduce_research_run!,
       entropy_bits, outcome_probabilities, likelihood_table, posterior,
       expected_information_gain, wilson_interval

const PROTOCOL_VERSION = "1.0"

mutable struct Client
    io::IO
    next_id::Int
end

struct ProtocolError <: Exception
    code::String
    message::String
end

Base.showerror(io::IO, error::ProtocolError) =
    print(io, "EigenBrains remote error ", error.code, ": ", error.message)

Base.@kwdef struct ResourceBudget
    max_evaluations::Union{Nothing,Int} = nothing
    max_seconds::Union{Nothing,Float64} = nothing
end

Base.@kwdef struct FieldSchema
    name::String
    dtype::String
    unit::Union{Nothing,String} = nothing
    role::Union{Nothing,String} = nothing
    nullable::Bool = false
    minimum::Union{Nothing,Float64} = nothing
    maximum::Union{Nothing,Float64} = nothing
    censoring::Union{Nothing,String} = nothing
end

Base.@kwdef struct ArtifactSchema
    name::String
    version::Int = 1
    kind::String
    fields::Vector{FieldSchema} = FieldSchema[]
    dtype::Union{Nothing,String} = nothing
    ndim::Union{Nothing,Int} = nothing
    unit::Union{Nothing,String} = nothing
    role::Union{Nothing,String} = nothing
    allow_extra_fields::Bool = false
end

Base.@kwdef struct MetricSpec
    name::String
    unit::String
    role::String = "secondary"
    minimum::Union{Nothing,Float64} = nothing
    maximum::Union{Nothing,Float64} = nothing
    censoring::Union{Nothing,String} = nothing
end

Base.@kwdef struct ResearchExperimentSpec
    capability::String
    hypothesis::String
    protocol::String
    parameters::Dict{String,Any} = Dict{String,Any}()
    seed::Int
    outputs::Vector{ArtifactSchema}
    primary_metric::MetricSpec
    budget::ResourceBudget = ResourceBudget()
    runner::Union{Nothing,String} = nothing
    inputs::Dict{String,String} = Dict{String,String}()
    reproduction_of::Union{Nothing,String} = nothing
end

asdict(value::ResourceBudget) = Dict(
    "max_evaluations" => value.max_evaluations, "max_seconds" => value.max_seconds,
)
asdict(value::FieldSchema) = Dict(
    "name" => value.name, "dtype" => value.dtype, "unit" => value.unit,
    "role" => value.role, "nullable" => value.nullable, "minimum" => value.minimum,
    "maximum" => value.maximum, "censoring" => value.censoring,
)
asdict(value::ArtifactSchema) = Dict(
    "name" => value.name, "version" => value.version, "kind" => value.kind,
    "fields" => asdict.(value.fields), "dtype" => value.dtype, "ndim" => value.ndim,
    "unit" => value.unit, "role" => value.role, "allow_extra_fields" => value.allow_extra_fields,
)
asdict(value::MetricSpec) = Dict(
    "name" => value.name, "unit" => value.unit, "role" => value.role,
    "minimum" => value.minimum, "maximum" => value.maximum, "censoring" => value.censoring,
)
asdict(value::ResearchExperimentSpec) = Dict(
    "capability" => value.capability, "hypothesis" => value.hypothesis,
    "protocol" => value.protocol, "parameters" => value.parameters, "seed" => value.seed,
    "outputs" => asdict.(value.outputs), "primary_metric" => asdict(value.primary_metric),
    "budget" => asdict(value.budget), "runner" => value.runner, "inputs" => value.inputs,
    "reproduction_of" => value.reproduction_of,
)

"""Start the persistent Python bridge used by the Julia SDK."""
function open_client(root::AbstractString; python::AbstractString="python", actor::AbstractString="julia-sdk")
    cmd = Cmd([python, "-m", "discolab.rpc", "--root", root, "--actor", actor])
    Client(open(cmd, "r+"), 1)
end

function request!(client::Client, method::AbstractString, params=Dict{String,Any}())
    id = client.next_id
    client.next_id += 1
    request = Dict("id" => id, "version" => PROTOCOL_VERSION, "method" => method, "params" => params)
    write(client.io, JSON.json(request), '\n')
    flush(client.io)
    response = JSON.parse(readline(client.io))
    get(response, "id", nothing) == id || error("EigenBrains response id mismatch")
    get(response, "version", nothing) == PROTOCOL_VERSION ||
        error("EigenBrains response protocol version mismatch")
    if !get(response, "ok", false)
        detail = get(response, "error", Dict{String,Any}())
        throw(ProtocolError(
            string(get(detail, "code", "UnknownError")),
            string(get(detail, "message", "unknown error")),
        ))
    end
    haskey(response, "result") || error("EigenBrains successful response omitted result")
    response["result"]
end

initialize!(client::Client) = request!(client, "initialize")
state(client::Client) = request!(client, "state")
events(client::Client) = request!(client, "events")
propose!(client::Client, experiment) = request!(client, "propose", Dict("experiment" => experiment))
score!(client::Client) = request!(client, "score")
select!(client::Client, id::AbstractString, why::AbstractString) =
    request!(client, "select", Dict("experiment_id" => id, "justification" => why))
run!(client::Client; confirm_heldout::Bool=false) =
    request!(client, "run", Dict("confirm_heldout" => confirm_heldout))
abort!(client::Client, id::AbstractString, reason::AbstractString) =
    request!(client, "abort", Dict("experiment_id" => id, "reason" => reason))
result(client::Client, id::AbstractString) =
    request!(client, "result", Dict("experiment_id" => id))
analyze!(
    client::Client,
    id::AbstractString,
    interpretation::AbstractString;
    threats_to_validity=String[],
) = request!(client, "analyze", Dict(
    "experiment_id" => id,
    "interpretation" => interpretation,
    "threats_to_validity" => collect(threats_to_validity),
))
decide!(
    client::Client,
    decision::AbstractString,
    rationale::AbstractString;
    next_experiment=nothing,
) = request!(client, "decide", Dict(
    "decision" => decision,
    "rationale" => rationale,
    "next_experiment" => next_experiment,
))
register_hypothesis!(client::Client, hypothesis) =
    request!(client, "register_hypothesis", hypothesis)

begin_research_run!(client::Client, spec::ResearchExperimentSpec) =
    request!(client, "research.begin", Dict("spec" => asdict(spec)))
emit_research_artifact!(
    client::Client, run_id::AbstractString, name::AbstractString, kind::AbstractString,
    value, schema::AbstractString; stage::AbstractString="raw", parents=String[],
) = request!(client, "research.emit", Dict(
    "run_id" => run_id, "name" => name, "kind" => kind, "value" => value,
    "schema" => schema, "stage" => stage, "parents" => collect(parents),
))
record_research_metric!(
    client::Client, run_id::AbstractString, name::AbstractString, value::Real;
    spec::Union{Nothing,MetricSpec}=nothing,
) = request!(client, "research.metric", Dict(
    "run_id" => run_id, "name" => name, "value" => Float64(value),
    "spec" => isnothing(spec) ? nothing : asdict(spec),
))
consume_research_budget!(client::Client, run_id::AbstractString, evaluations::Integer=0) =
    request!(client, "research.consume", Dict("run_id" => run_id, "evaluations" => evaluations))
finalize_research_run!(client::Client, run_id::AbstractString) =
    request!(client, "research.finalize", Dict("run_id" => run_id))
inspect_research_run(client::Client, run_id::AbstractString) =
    request!(client, "research.inspect", Dict("run_id" => run_id))
validate_research_run(client::Client, run_id::AbstractString) =
    request!(client, "research.validate", Dict("run_id" => run_id))
compare_research_runs(client::Client, left::AbstractString, right::AbstractString) =
    request!(client, "research.compare", Dict("left" => left, "right" => right))
accept_research_run!(client::Client, run_id::AbstractString, rationale::AbstractString) =
    request!(client, "research.accept", Dict("run_id" => run_id, "rationale" => rationale))
reproduce_research_run!(client::Client, run_id::AbstractString) =
    request!(client, "research.reproduce", Dict("run_id" => run_id))

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
