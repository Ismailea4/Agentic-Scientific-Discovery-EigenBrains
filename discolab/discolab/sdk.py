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
from .bundle import export_bundle, verify_bundle
from .evidence import (
    ArtifactSchema,
    EvidenceError,
    EvidenceStore,
    ExperimentSpecV2,
    MetricSpec,
    RunContext,
    _validate_name,
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

    def __init__(self, root: str | Path, *, actor: str = "python-sdk",
                 allowed_runner_modules: Iterable[str] | None = None):
        self.root = Path(root).resolve()
        self.actor = actor
        # None: trusted in-process caller, any importable runner may be named.
        # A collection (the RPC bridge): a runner is imported only when its module
        # is listed or is a submodule of a listed module; by default none is.
        self.allowed_runner_modules = None if allowed_runner_modules is None else tuple(allowed_runner_modules)
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
        self._check_runner(parsed.runner)
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
        context = self._research_context(run_id)
        try:
            return context.finalize()
        finally:
            if not context.is_open:
                self._research_contexts.pop(run_id, None)

    def inspect_research_run(self, run_id: str) -> dict[str, Any]:
        return EvidenceStore(self.root).inspect(run_id)

    def validate_research_run(self, run_id: str) -> dict[str, Any]:
        return EvidenceStore(self.root).validate(run_id)

    def compare_research_runs(self, left: str, right: str) -> dict[str, Any]:
        return EvidenceStore(self.root).compare(left, right)

    def accept_research_run(self, run_id: str, rationale: str) -> dict[str, Any]:
        return EvidenceStore(self.root).accept(run_id, rationale)

    def reject_research_run(self, run_id: str, reason: str) -> dict[str, Any]:
        return EvidenceStore(self.root).reject(run_id, reason)

    def reproduce_research_run(self, run_id: str) -> dict[str, Any]:
        self._check_runner(EvidenceStore(self.root).inspect(run_id)["spec"].get("runner"))
        return EvidenceStore(self.root).reproduce(run_id)

    def list_research_runs(
        self,
        *,
        capability: str | None = None,
        status: str | None = None,
        seed: int | None = None,
        created_after: Any = None,
        created_before: Any = None,
    ) -> list[dict[str, Any]]:
        return EvidenceStore(self.root).list(capability=capability, status=status, seed=seed,
                                             created_after=created_after, created_before=created_before)

    def checkpoint_research_run(self, run_id: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._research_context(run_id).checkpoint(state)

    def resume_research_run(self, run_id: str) -> dict[str, Any]:
        """Reopen an interrupted run in this process from its last checkpoint. The
        caller continues it with emit/metric/consume/finalize; no code is executed."""
        if run_id in self._research_contexts:
            raise EvidenceError(f"run {run_id} is already open in this SDK process")
        self._check_runner(EvidenceStore(self.root).inspect(run_id)["spec"].get("runner"))
        context = EvidenceStore(self.root).resume(run_id)
        self._research_contexts[run_id] = context
        return {"run_id": run_id, "status": "running", "checkpoint_sequence": context.resumed_from,
                "state": context.restored_state, "evaluations": context.evaluations,
                "elapsed_seconds": context.elapsed_seconds, "artifacts": sorted(context._artifacts),
                "metrics": sorted(context._metrics)}

    def fail_research_run(self, run_id: str, error_type: str, message: str) -> dict[str, Any]:
        """Record that the client's experiment code failed; the run becomes failed."""
        _validate_name(error_type, "error type")
        self._research_context(run_id).record_failure(error_type, message)
        self._research_contexts.pop(run_id, None)
        return {"run_id": run_id, "status": "failed"}

    def research_lineage(self) -> dict[str, Any]:
        return EvidenceStore(self.root).lineage()

    def export_research_bundle(self, run_ids: Iterable[str], name: str) -> dict[str, Any]:
        """Export runs to ``<root>/bundles/<name>.zip`` (names only, never a free path)."""
        manifest = export_bundle(self.root, run_ids, self._bundle_path(name))
        return {"name": name, "path": f"bundles/{name}.zip", "content_sha256": manifest["content_sha256"],
                "runs": manifest["runs"], "files": len(manifest["files"])}

    def verify_research_bundle(self, name: str) -> dict[str, Any]:
        return {"name": name, **verify_bundle(self._bundle_path(name))}

    def describe(self) -> dict[str, Any]:
        from .rpc import METHODS

        return {"protocol_version": PROTOCOL_VERSION, "methods": sorted(METHODS),
                "runner_policy": "any" if self.allowed_runner_modules is None else
                ("allow-list" if self.allowed_runner_modules else "none"),
                "requires_python_sidecar": True}

    def _bundle_path(self, name: str) -> Path:
        _validate_name(name, "bundle")
        return self.root / "bundles" / f"{name}.zip"

    def _check_runner(self, runner: str | None) -> None:
        if runner is None or self.allowed_runner_modules is None:
            return
        module = runner.partition(":")[0]
        if not any(module == m or module.startswith(m + ".") for m in self.allowed_runner_modules):
            raise PermissionError(f"runner module {module!r} is not allow-listed for this bridge; "
                                  "start it with --allow-runner-module to permit importing it")

    def _research_context(self, run_id: str) -> RunContext:
        try:
            context = self._research_contexts[run_id]
        except KeyError as exc:
            raise KeyError(f"no open research run {run_id!r} in this SDK process") from exc
        if not context.is_open:
            self._research_contexts.pop(run_id, None)
            raise EvidenceError(f"run {run_id} is closed")
        return context
