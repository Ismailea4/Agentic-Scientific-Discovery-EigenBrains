"""Public Python SDK for the EigenBrains scientific-discovery runtime.

The SDK is deliberately a thin facade over :mod:`discolab.lab`.  It does not
duplicate experiment logic, statistics, or ledger transitions; Python users,
Omnigent tools, and the language-neutral RPC bridge therefore exercise the
same validated code paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import lab
from .evidence import (
    ArtifactSchema,
    EvidenceStore,
    ExperimentSpecV2,
    MetricSpec,
    RunContext,
)
from .ledger import Ledger
from .views import result_summary

PROTOCOL_VERSION = "1.0"


@dataclass(frozen=True)
class Experiment:
    """JSON-serialisable experiment specification accepted by the lab."""

    kind: str
    title: str
    rationale: str
    hypotheses: tuple[str, ...]
    landscapes: tuple[str, ...]
    n_seeds: int
    feature_sets: tuple[str, ...] | None = None
    controllers: tuple[str, ...] | None = None

    @classmethod
    def prediction(
        cls,
        *,
        title: str,
        rationale: str,
        hypotheses: Iterable[str],
        landscapes: Iterable[str],
        n_seeds: int,
        feature_sets: Iterable[str],
    ) -> "Experiment":
        return cls("prediction", title, rationale, tuple(hypotheses), tuple(landscapes), n_seeds,
                   feature_sets=tuple(feature_sets))

    @classmethod
    def control(
        cls,
        *,
        title: str,
        rationale: str,
        hypotheses: Iterable[str],
        landscapes: Iterable[str],
        n_seeds: int,
        controllers: Iterable[str],
    ) -> "Experiment":
        return cls("control", title, rationale, tuple(hypotheses), tuple(landscapes), n_seeds,
                   controllers=tuple(controllers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "rationale": self.rationale,
            "hypotheses": list(self.hypotheses),
            "landscapes": list(self.landscapes),
            "n_seeds": self.n_seeds,
            "feature_sets": list(self.feature_sets) if self.feature_sets is not None else None,
            "controllers": list(self.controllers) if self.controllers is not None else None,
        }


class DiscoveryLab:
    """Operate one persistent, replayable research lab.

    Parameters
    ----------
    root:
        Directory containing ``ledger.jsonl`` and immutable experiment artifacts.
    actor:
        Provenance label written on every transition initiated by this client.
    """

    def __init__(self, root: str | Path, *, actor: str = "python-sdk"):
        self.root = Path(root).resolve()
        self.actor = actor
        self._research_contexts: dict[str, RunContext] = {}

    @property
    def protocol_version(self) -> str:
        return PROTOCOL_VERSION

    @property
    def initialized(self) -> bool:
        return bool(Ledger(self.root).events())

    def initialize(self) -> dict[str, Any]:
        return lab.init_lab(self.root, self.actor)

    def state(self) -> dict[str, Any]:
        return lab.get_state(self.root)

    def events(self) -> list[dict[str, Any]]:
        return Ledger(self.root).events()

    def propose(self, experiment: Experiment | dict[str, Any]) -> dict[str, Any]:
        spec = experiment.to_dict() if isinstance(experiment, Experiment) else experiment
        return lab.propose_experiment(spec, self.actor, self.root)

    def score(self) -> dict[str, Any]:
        return lab.score_experiments(self.actor, self.root)

    def select(self, experiment_id: str, justification: str) -> dict[str, Any]:
        return lab.select_experiment(experiment_id, justification, self.actor, self.root)

    def run(self, *, confirm_heldout: bool = False) -> dict[str, Any]:
        state = Ledger(self.root).state()
        selected = state.get("selected")
        candidate = state.get("candidates", {}).get(selected) if selected else None
        if candidate and candidate.get("derived", {}).get("stage") == "confirmatory" and not confirm_heldout:
            raise PermissionError(
                "confirmatory execution spends held-out data; call run(confirm_heldout=True) "
                "only after recording human approval"
            )
        return lab.run_selected_experiment(self.actor, self.root)

    def abort(self, experiment_id: str, reason: str) -> dict[str, Any]:
        return lab.abort_experiment(experiment_id, reason, self.actor, self.root)

    def result(self, experiment_id: str) -> dict[str, Any]:
        state = Ledger(self.root).state()
        if experiment_id not in state["candidates"]:
            raise KeyError(f"unknown experiment {experiment_id}")
        return result_summary(state["candidates"][experiment_id])

    def analyze(
        self,
        experiment_id: str,
        interpretation: str,
        threats_to_validity: Iterable[str] = (),
    ) -> dict[str, Any]:
        return lab.record_analysis(experiment_id, interpretation, list(threats_to_validity), self.actor, self.root)

    def decide(self, decision: str, rationale: str, next_experiment: str | None = None) -> dict[str, Any]:
        return lab.record_decision(decision, rationale, next_experiment, self.actor, self.root)

    def register_hypothesis(self, **spec: Any) -> dict[str, Any]:
        return lab.register_hypothesis(
            spec["hypothesis_id"], spec["statement"], spec["h0"], spec["family"],
            spec.get("feature_set"), spec.get("controller"), self.actor, self.root,
            baseline_feature_set=spec.get("baseline_feature_set"), comparator=spec.get("comparator"),
        )

    # Generic, domain-independent evidence runs. These methods are also the
    # stable boundary used by the Rust and Julia bridge clients.
    def begin_research_run(self, spec: ExperimentSpecV2 | dict[str, Any]) -> dict[str, Any]:
        parsed = spec if isinstance(spec, ExperimentSpecV2) else ExperimentSpecV2.from_dict(spec)
        context = EvidenceStore(self.root).begin(parsed)
        self._research_contexts[context.run_id] = context
        return {"run_id": context.run_id, "status": "running", "seed": context.seed}

    def emit_research_artifact(
        self,
        run_id: str,
        *,
        name: str,
        kind: str,
        value: Any,
        schema: str | dict[str, Any],
        stage: str = "raw",
        parents: Iterable[str] = (),
    ) -> dict[str, Any]:
        context = self._research_context(run_id)
        resolved = ArtifactSchema.from_dict(schema) if isinstance(schema, dict) else schema
        kwargs = {"schema": resolved, "stage": stage, "parents": tuple(parents)}
        if kind == "table":
            return context.emit.table(name, value, **kwargs)
        if kind == "array":
            return context.emit.array(name, value, **kwargs)
        if kind == "json":
            return context.emit.json(name, value, **kwargs)
        raise ValueError(f"unknown artifact kind {kind!r}")

    def record_research_metric(
        self,
        run_id: str,
        name: str,
        value: float,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed = MetricSpec.from_dict(spec) if spec is not None else None
        return self._research_context(run_id).metric(name, value, spec=parsed)

    def consume_research_budget(self, run_id: str, evaluations: int = 0) -> dict[str, Any]:
        context = self._research_context(run_id)
        context.consume(evaluations)
        return {"run_id": run_id, "evaluations": context.evaluations,
                "elapsed_seconds": context.elapsed_seconds}

    def finalize_research_run(self, run_id: str) -> dict[str, Any]:
        result = self._research_context(run_id).finalize()
        self._research_contexts.pop(run_id, None)
        return result

    def inspect_research_run(self, run_id: str) -> dict[str, Any]:
        return EvidenceStore(self.root).inspect(run_id)

    def validate_research_run(self, run_id: str) -> dict[str, Any]:
        return EvidenceStore(self.root).validate(run_id)

    def compare_research_runs(self, left: str, right: str) -> dict[str, Any]:
        return EvidenceStore(self.root).compare(left, right)

    def accept_research_run(self, run_id: str, rationale: str) -> dict[str, Any]:
        return EvidenceStore(self.root).accept(run_id, rationale)

    def reproduce_research_run(self, run_id: str) -> dict[str, Any]:
        return EvidenceStore(self.root).reproduce(run_id)

    def _research_context(self, run_id: str) -> RunContext:
        try:
            return self._research_contexts[run_id]
        except KeyError as exc:
            raise KeyError(f"no open research run {run_id!r} in this SDK process") from exc
