module EigenBrainsSDK

using JSON
using Distributions
using FastGaussQuadrature

export Client, ProtocolError, ContractError, open_client, request!, describe, initialize!, state, events,
       propose!, score!, select!, run!, abort!, result, analyze!, decide!,
       register_hypothesis!, METHODS,
       ResourceBudget, FieldSchema, ArtifactSchema, MetricSpec, ResearchExperimentSpec,
       field_schema, table_schema, array_schema, json_schema, metric_spec, research_spec,
       validate, schema_id, spec_dict, spec_from_dict,
       begin_research_run!, emit_research_artifact!, record_research_metric!,
       consume_research_budget!, checkpoint_research_run!, resume_research_run!, fail_research_run!,
       finalize_research_run!, inspect_research_run, validate_research_run, list_research_runs,
       compare_research_runs, accept_research_run!, reject_research_run!, reproduce_research_run!,
       research_lineage, export_research_bundle!, verify_research_bundle,
       with_research_run, with_resumed_research_run,
       entropy_bits, outcome_probabilities, likelihood_table, posterior,
       expected_information_gain, wilson_interval,
       auroc, clustered_auroc, paired_clustered_auroc

const PROTOCOL_VERSION = "1.0"

"""Every protocol-v1 method this client implements (tested against the schema)."""
const METHODS = [
    "describe", "initialize", "state", "events", "propose", "score", "select", "run", "abort",
    "result", "analyze", "decide", "register_hypothesis",
    "research.begin", "research.emit", "research.metric", "research.consume",
    "research.checkpoint", "research.resume", "research.fail", "research.finalize",
    "research.inspect", "research.validate", "research.list", "research.compare",
    "research.accept", "research.reject", "research.reproduce", "research.lineage",
    "research.export_bundle", "research.verify_bundle",
]

const FIELD_DTYPES = ("number", "integer", "string", "boolean")
const ARTIFACT_KINDS = ("table", "array", "json")
const METRIC_ROLES = ("primary", "secondary", "diagnostic")
const CENSORING = ("right", "left", "interval")
const NAME_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$"

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

"""Raised locally when an evidence contract is invalid (nothing is sent)."""
struct ContractError <: Exception
    message::String
end

Base.showerror(io::IO, error::ContractError) = print(io, "invalid evidence contract: ", error.message)

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

# ---------------------------------------------------------------- validation (mirrors Python)

_check(cond::Bool, message) = cond || throw(ContractError(message))
_name(value, kind) = _check(occursin(NAME_PATTERN, value), "invalid $kind name $(repr(value))")
function _range(lo, hi, label)
    isnothing(lo) || isnothing(hi) || _check(lo <= hi, "$label: minimum exceeds maximum")
end

schema_id(schema::ArtifactSchema) = "$(schema.name).v$(schema.version)"

function validate(budget::ResourceBudget)
    isnothing(budget.max_evaluations) || _check(budget.max_evaluations > 0, "max_evaluations must be positive")
    isnothing(budget.max_seconds) || _check(budget.max_seconds > 0, "max_seconds must be positive")
    budget
end

function validate(field::FieldSchema)
    _name(field.name, "field")
    _check(field.dtype in FIELD_DTYPES, "field $(field.name): unknown dtype $(repr(field.dtype))")
    numeric = field.dtype in ("number", "integer")
    _check(numeric || (isnothing(field.minimum) && isnothing(field.maximum) && isnothing(field.censoring)),
           "field $(field.name): ranges and censoring require a numeric dtype")
    _range(field.minimum, field.maximum, "field $(field.name)")
    isnothing(field.censoring) || _check(field.censoring in CENSORING,
                                         "field $(field.name): unknown censoring $(repr(field.censoring))")
    field
end

function validate(schema::ArtifactSchema)
    _name(schema.name, "schema")
    _check(schema.version > 0, "schema version must be positive")
    _check(schema.kind in ARTIFACT_KINDS, "schema $(schema.name): unknown kind $(repr(schema.kind))")
    _check(schema.kind != "table" || !isempty(schema.fields), "table schemas require at least one field")
    _check(schema.kind != "array" || !(isnothing(schema.dtype) || isempty(schema.dtype)),
           "array schemas require dtype")
    isnothing(schema.ndim) || _check(schema.ndim >= 0, "ndim cannot be negative")
    foreach(validate, schema.fields)
    names = [f.name for f in schema.fields]
    _check(length(names) == length(unique(names)), "schema $(schema.name): field names must be unique")
    schema
end

function validate(metric::MetricSpec)
    _name(metric.name, "metric")
    _check(!isempty(metric.unit), "metric $(metric.name) requires a unit")
    _check(metric.role in METRIC_ROLES, "metric $(metric.name): unknown role $(repr(metric.role))")
    _range(metric.minimum, metric.maximum, "metric $(metric.name)")
    metric
end

function validate(spec::ResearchExperimentSpec)
    _name(spec.capability, "capability")
    _check(!isempty(strip(spec.hypothesis)), "hypothesis cannot be empty")
    _check(!isempty(strip(spec.protocol)), "protocol cannot be empty")
    _check(spec.seed >= 0, "seed must be a non-negative integer")
    _check(!isempty(spec.outputs), "at least one output schema is required")
    foreach(validate, spec.outputs)
    ids = schema_id.(spec.outputs)
    _check(length(ids) == length(unique(ids)), "output schema ids must be unique")
    validate(spec.primary_metric)
    validate(spec.budget)
    foreach(name -> _name(name, "input"), keys(spec.inputs))
    spec
end

# ---------------------------------------------------------------- builders

"""Validated field: `field_schema("loss", "number"; unit="objective", minimum=0.0)`."""
field_schema(name, dtype; kwargs...) = validate(FieldSchema(; name=String(name), dtype=String(dtype), kwargs...))
table_schema(name, fields::AbstractVector; version=1, kwargs...) =
    validate(ArtifactSchema(; name=String(name), version, kind="table", fields=collect(FieldSchema, fields), kwargs...))
array_schema(name, dtype; version=1, kwargs...) =
    validate(ArtifactSchema(; name=String(name), version, kind="array", dtype=String(dtype), kwargs...))
json_schema(name; version=1, kwargs...) = validate(ArtifactSchema(; name=String(name), version, kind="json", kwargs...))
metric_spec(name, unit; kwargs...) = validate(MetricSpec(; name=String(name), unit=String(unit), kwargs...))
"""Validated spec: `research_spec(capability, hypothesis, protocol; seed, outputs, primary_metric, ...)`."""
research_spec(capability, hypothesis, protocol; kwargs...) = validate(ResearchExperimentSpec(;
    capability=String(capability), hypothesis=String(hypothesis), protocol=String(protocol), kwargs...))

# ---------------------------------------------------------------- canonical JSON form

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
    "id" => schema_id(value),
)
asdict(value::MetricSpec) = Dict(
    "name" => value.name, "unit" => value.unit, "role" => value.role,
    "minimum" => value.minimum, "maximum" => value.maximum, "censoring" => value.censoring,
)
asdict(value::ResearchExperimentSpec) = Dict(
    "spec_version" => 2,
    "capability" => value.capability, "hypothesis" => value.hypothesis,
    "protocol" => value.protocol, "parameters" => value.parameters, "seed" => value.seed,
    "outputs" => asdict.(value.outputs), "primary_metric" => asdict(value.primary_metric),
    "budget" => asdict(value.budget), "runner" => value.runner, "inputs" => value.inputs,
    "reproduction_of" => value.reproduction_of,
)

"""Canonical protocol JSON of a spec (as a Dict)."""
spec_dict(spec::ResearchExperimentSpec) = asdict(validate(spec))

_opt(d, key, T) = (v = get(d, key, nothing); isnothing(v) ? nothing : convert(T, v))
_float(d, key) = (v = get(d, key, nothing); isnothing(v) ? nothing : Float64(v))

function _field_from(d)
    FieldSchema(; name=String(d["name"]), dtype=String(d["dtype"]), unit=_opt(d, "unit", String),
                role=_opt(d, "role", String), nullable=Bool(get(d, "nullable", false)),
                minimum=_float(d, "minimum"), maximum=_float(d, "maximum"),
                censoring=_opt(d, "censoring", String))
end

function _schema_from(d)
    ArtifactSchema(; name=String(d["name"]), version=Int(d["version"]), kind=String(d["kind"]),
                   fields=FieldSchema[_field_from(f) for f in something(get(d, "fields", nothing), [])],
                   dtype=_opt(d, "dtype", String), ndim=_opt(d, "ndim", Int), unit=_opt(d, "unit", String),
                   role=_opt(d, "role", String), allow_extra_fields=Bool(get(d, "allow_extra_fields", false)))
end

"""Parse and validate canonical JSON produced by any SDK language."""
function spec_from_dict(d::AbstractDict)
    version = get(d, "spec_version", 2)
    version == 2 || throw(ContractError("ExperimentSpecV2 requires spec_version 2, received $(repr(version))"))
    m = d["primary_metric"]
    metric = MetricSpec(; name=String(m["name"]), unit=String(m["unit"]), role=String(get(m, "role", "secondary")),
                        minimum=_float(m, "minimum"), maximum=_float(m, "maximum"),
                        censoring=_opt(m, "censoring", String))
    b = something(get(d, "budget", nothing), Dict())
    inputs = Dict{String,String}(String(k) => String(v) for (k, v) in something(get(d, "inputs", nothing), Dict()))
    validate(ResearchExperimentSpec(;
        capability=String(d["capability"]), hypothesis=String(d["hypothesis"]), protocol=String(d["protocol"]),
        parameters=Dict{String,Any}(String(k) => v for (k, v) in something(get(d, "parameters", nothing), Dict())),
        seed=Int(d["seed"]), outputs=ArtifactSchema[_schema_from(o) for o in d["outputs"]],
        primary_metric=metric,
        budget=ResourceBudget(; max_evaluations=_opt(b, "max_evaluations", Int), max_seconds=_float(b, "max_seconds")),
        runner=_opt(d, "runner", String), inputs, reproduction_of=_opt(d, "reproduction_of", String)))
end

# ---------------------------------------------------------------- bridge

"""Start the persistent Python sidecar (required: Julia is a client of the Python runtime).
`allowed_runner_modules` permits runs naming an importable Python runner (default: none)."""
function open_client(root::AbstractString; python::AbstractString="python", actor::AbstractString="julia-sdk",
                     allowed_runner_modules=String[])
    args = String[python, "-m", "discolab.rpc", "--root", root, "--actor", actor]
    for module_name in allowed_runner_modules
        append!(args, ["--allow-runner-module", module_name])
    end
    Client(open(Cmd(args), "r+"), 1)
end

function request!(client::Client, method::AbstractString, params=Dict{String,Any}())
    id = client.next_id
    client.next_id += 1
    request = Dict("id" => id, "version" => PROTOCOL_VERSION, "method" => method, "params" => params)
    write(client.io, JSON.json(request), '\n')
    flush(client.io)
    line = readline(client.io)
    isempty(line) && error("EigenBrains bridge closed before replying")
    response = JSON.parse(line)
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

describe(client::Client) = request!(client, "describe")
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
    request!(client, "research.begin", Dict("spec" => spec_dict(spec)))
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
    "spec" => isnothing(spec) ? nothing : asdict(validate(spec)),
))
consume_research_budget!(client::Client, run_id::AbstractString, evaluations::Integer=0) =
    request!(client, "research.consume", Dict("run_id" => run_id, "evaluations" => evaluations))
checkpoint_research_run!(client::Client, run_id::AbstractString, state=Dict{String,Any}()) =
    request!(client, "research.checkpoint", Dict("run_id" => run_id, "state" => state))
resume_research_run!(client::Client, run_id::AbstractString) =
    request!(client, "research.resume", Dict("run_id" => run_id))
fail_research_run!(client::Client, run_id::AbstractString, error_type::AbstractString, message::AbstractString) =
    request!(client, "research.fail", Dict("run_id" => run_id, "error_type" => error_type, "message" => message))
finalize_research_run!(client::Client, run_id::AbstractString) =
    request!(client, "research.finalize", Dict("run_id" => run_id))
inspect_research_run(client::Client, run_id::AbstractString) =
    request!(client, "research.inspect", Dict("run_id" => run_id))
validate_research_run(client::Client, run_id::AbstractString) =
    request!(client, "research.validate", Dict("run_id" => run_id))
"""Filters: capability, status, seed, created_after, created_before (ISO-8601, inclusive)."""
function list_research_runs(client::Client; filters...)
    params = Dict{String,Any}(String(k) => v for (k, v) in filters if !isnothing(v))
    request!(client, "research.list", params)
end
compare_research_runs(client::Client, left::AbstractString, right::AbstractString) =
    request!(client, "research.compare", Dict("left" => left, "right" => right))
accept_research_run!(client::Client, run_id::AbstractString, rationale::AbstractString) =
    request!(client, "research.accept", Dict("run_id" => run_id, "rationale" => rationale))
reject_research_run!(client::Client, run_id::AbstractString, reason::AbstractString) =
    request!(client, "research.reject", Dict("run_id" => run_id, "reason" => reason))
reproduce_research_run!(client::Client, run_id::AbstractString) =
    request!(client, "research.reproduce", Dict("run_id" => run_id))
research_lineage(client::Client) = request!(client, "research.lineage")
"""Writes `<lab root>/bundles/<name>.zip`; `name` must be a plain name."""
export_research_bundle!(client::Client, run_ids, name::AbstractString) =
    request!(client, "research.export_bundle", Dict("run_ids" => collect(run_ids), "name" => name))
verify_research_bundle(client::Client, name::AbstractString) =
    request!(client, "research.verify_bundle", Dict("name" => name))

_failure_type(error) = error isa ProtocolError ? "RemoteError" :
                       error isa ContractError ? "JuliaContractError" : "Julia" * string(nameof(typeof(error)))

function _drive(f, client::Client, run_id)
    value = try
        f()
    catch error
        try
            fail_research_run!(client, run_id, _failure_type(error), sprint(showerror, error))
        catch
        end
        rethrow()
    end
    report = try
        finalize_research_run!(client, run_id)
    catch error
        try
            fail_research_run!(client, run_id, _failure_type(error), sprint(showerror, error))
        catch
        end
        rethrow()
    end
    (value, report)
end

"""
    with_research_run(client, spec) do run_id ... end

Open a run, finalize it when the block returns, and record it as failed (then
rethrow) if the block or finalization throws. Returns `(block value, report)`.
"""
function with_research_run(f, client::Client, spec::ResearchExperimentSpec)
    run_id = begin_research_run!(client, spec)["run_id"]
    _drive(() -> f(run_id), client, run_id)
end

"""
    with_resumed_research_run(client, run_id) do run_id, state ... end

Reopen an interrupted run from its last checkpoint; the block receives the saved state.
"""
function with_resumed_research_run(f, client::Client, run_id::AbstractString)
    resumed = resume_research_run!(client, run_id)
    _drive(() -> f(run_id, resumed["state"]), client, run_id)
end

Base.close(client::Client) = close(client.io)

# ---------------------------------------------------------------- decision mathematics

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

# ---------------------------------------------------------------- ROC statistics

"""Structural components (DeLong et al. 1988): for each positive, the fraction of
negatives it outranks (ties count 1/2), and for each negative the fraction of
positives that outrank it. Their means both equal the AUROC."""
function _components(scores::AbstractVector{<:Real}, labels::AbstractVector{Bool})
    pos = scores[labels]
    neg = scores[.!labels]
    m, n = length(pos), length(neg)
    (m > 0 && n > 0) || throw(ArgumentError("AUROC needs both classes"))
    negs, poss = sort(neg), sort(pos)
    v10 = [(searchsortedfirst(negs, s) - 1 + 0.5 * (searchsortedlast(negs, s) - searchsortedfirst(negs, s) + 1)) / n
           for s in pos]
    v01 = [(m - searchsortedlast(poss, s) + 0.5 * (searchsortedlast(poss, s) - searchsortedfirst(poss, s) + 1)) / m
           for s in neg]
    v10, v01
end

"""Mann-Whitney AUROC with average ranks for ties (matches Python `discolab.stats.auroc`)."""
auroc(scores, labels) = sum(first(_components(Float64.(scores), collect(Bool, labels)))) / count(Bool, labels)

function _cluster_terms(scores, labels::AbstractVector{Bool}, clusters)
    v10, v01 = _components(Float64.(scores), labels)
    theta = sum(v10) / length(v10)
    ids = unique(clusters)
    index = Dict(c => i for (i, c) in enumerate(ids))
    k = length(ids)
    V10, V01, m, n = zeros(k), zeros(k), zeros(k), zeros(k)
    ip, in_ = 0, 0
    for (j, c) in enumerate(clusters)
        i = index[c]
        if labels[j]
            ip += 1
            V10[i] += v10[ip]
            m[i] += 1
        else
            in_ += 1
            V01[i] += v01[in_]
            n[i] += 1
        end
    end
    (theta=theta, a=V10 .- m .* theta, b=V01 .- n .* theta, m=m, n=n, k=k)
end

function _covariance(x, y)
    M, N = sum(x.m), sum(x.n)
    I10, I01, I = count(>(0), x.m), count(>(0), x.n), x.k
    (I10 > 1 && I01 > 1) || throw(ArgumentError("need at least two clusters with each class"))
    s10 = I10 / ((I10 - 1) * M) * sum(x.a .* y.a)
    s01 = I01 / ((I01 - 1) * N) * sum(x.b .* y.b)
    s11 = I / (I - 1) * sum(x.a .* y.b)
    s11t = I / (I - 1) * sum(y.a .* x.b)
    s10 / M + s01 / N + (s11 + s11t) / (M * N)
end

"""
    clustered_auroc(scores, labels, clusters; level=0.95)

AUROC with the nonparametric variance of Obuchowski (1997, Biometrics 53:567-578)
for clustered observations (here: generations nested in runs). With one
observation per cluster it reduces to DeLong et al. (1988).
"""
function clustered_auroc(scores, labels, clusters; level::Real=0.95)
    t = _cluster_terms(scores, collect(Bool, labels), clusters)
    se = sqrt(max(_covariance(t, t), 0.0))
    z = quantile(Normal(), 1 - (1 - level) / 2)
    (estimate=t.theta, se=se, low=t.theta - z * se, high=t.theta + z * se, clusters=t.k)
end

"""
    paired_clustered_auroc(scores_a, scores_b, labels, clusters; level=0.95)

Difference AUROC(a) - AUROC(b) for two scores on the same observations, with the
Obuchowski clustered covariance; returns estimate, SE, Wald CI and two-sided p.
"""
function paired_clustered_auroc(scores_a, scores_b, labels, clusters; level::Real=0.95)
    y = collect(Bool, labels)
    ta = _cluster_terms(scores_a, y, clusters)
    tb = _cluster_terms(scores_b, y, clusters)
    variance = _covariance(ta, ta) + _covariance(tb, tb) - 2 * _covariance(ta, tb)
    se = sqrt(max(variance, 0.0))
    delta = ta.theta - tb.theta
    z = quantile(Normal(), 1 - (1 - level) / 2)
    p = se > 0 ? 2 * ccdf(Normal(), abs(delta) / se) : (delta == 0 ? 1.0 : 0.0)
    (estimate=delta, se=se, low=delta - z * se, high=delta + z * se, p=p,
     auroc_a=ta.theta, auroc_b=tb.theta, clusters=ta.k)
end

end
