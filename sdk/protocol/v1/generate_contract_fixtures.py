"""Regenerate contract-fixtures.json from the authoritative Python types.

Run from the discolab directory:  python ../sdk/protocol/v1/generate_contract_fixtures.py
The Rust and Julia test suites read the output; Python's tests check it is current.
"""

import copy
import json
from pathlib import Path

from discolab import ArtifactSchema, ExperimentSpecV2, FieldSchema, MetricSpec, ResourceBudget
from discolab.rpc import METHODS

OUT = Path(__file__).with_name("contract-fixtures.json")


def canonical_spec() -> dict:
    return ExperimentSpecV2(
        capability="optimization",
        hypothesis="Population entropy adds early-warning information beyond fitness history.",
        protocol="protocols/early-warning-v1.yaml",
        parameters={"population": 50, "landscape": "rastrigin", "rates": [0.5, 1.0, 2.0],
                    "nested": {"horizon": 10}},
        seed=2026,
        outputs=(
            ArtifactSchema("trajectory", 1, "table", fields=(
                FieldSchema("generation", "integer", unit="generations", role="index", minimum=0.0),
                FieldSchema("best_error", "number", unit="objective", role="observation", minimum=0.0),
                FieldSchema("entropy", "number", unit="normalized_entropy", role="observation",
                            minimum=0.0, maximum=1.0),
                FieldSchema("recovery", "number", unit="generations", role="outcome", nullable=True,
                            minimum=0.0, censoring="right"),
                FieldSchema("landscape", "string", role="stratum"),
                FieldSchema("improved", "boolean", role="label"),
            )),
            ArtifactSchema("populations", 2, "array", dtype="float64", ndim=3, unit="decision_space",
                           role="state"),
            ArtifactSchema("summary", 1, "json", role="analysis"),
        ),
        primary_metric=MetricSpec("delta_auroc", "auroc", role="primary", minimum=-1.0, maximum=1.0),
        budget=ResourceBudget(max_evaluations=100000, max_seconds=600.0),
    ).to_dict()


# (case, JSON path into the canonical spec, replacement value): every language must reject each.
INVALID = [
    ("capability must match the name pattern", ["capability"], "1optimization"),
    ("hypothesis cannot be blank", ["hypothesis"], "   "),
    ("protocol cannot be empty", ["protocol"], ""),
    ("seed must be non-negative", ["seed"], -1),
    ("at least one output", ["outputs"], []),
    ("output ids must be unique", ["outputs", 2, "name"], "trajectory"),
    ("schema version must be positive", ["outputs", 2, "version"], 0),
    ("schema kind must be known", ["outputs", 2, "kind"], "graph"),
    ("table schemas need fields", ["outputs", 0, "fields"], []),
    ("array schemas need a dtype", ["outputs", 1, "dtype"], None),
    ("field dtype must be known", ["outputs", 0, "fields", 1, "dtype"], "complex"),
    ("ranges require a numeric field", ["outputs", 0, "fields", 4, "minimum"], 0.0),
    ("field minimum cannot exceed maximum", ["outputs", 0, "fields", 2, "minimum"], 2.0),
    ("censoring must be known", ["outputs", 0, "fields", 3, "censoring"], "sideways"),
    ("field names must be unique", ["outputs", 0, "fields", 1, "name"], "generation"),
    ("metric needs a unit", ["primary_metric", "unit"], ""),
    ("metric role must be known", ["primary_metric", "role"], "tertiary"),
    ("metric minimum cannot exceed maximum", ["primary_metric", "minimum"], 2.0),
    ("evaluation budget must be positive", ["budget", "max_evaluations"], 0),
    ("time budget must be positive", ["budget", "max_seconds"], -1.0),
    ("input names must match the name pattern", ["inputs"], {"bad name": "data.csv"}),
]


def apply(spec: dict, path: list, value) -> dict:
    out = copy.deepcopy(spec)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def build() -> dict:
    canonical = canonical_spec()
    assert ExperimentSpecV2.from_dict(canonical).to_dict() == canonical
    for case, path, value in INVALID:
        try:
            ExperimentSpecV2.from_dict(apply(canonical, path, value))
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"the Python contract accepted an invalid case: {case}")
    return {
        "generated_by": "discolab Python authoritative implementation (ExperimentSpecV2)",
        "protocol_version": "1.0",
        "name_pattern": "^[A-Za-z][A-Za-z0-9_.-]{0,127}$",
        "methods": list(METHODS),
        "canonical_spec": canonical,
        "invalid_specs": [{"case": c, "path": p, "value": v} for c, p, v in INVALID],
    }


def render() -> str:
    return json.dumps(build(), indent=2) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.name}")
