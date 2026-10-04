"""discolab: an Omnigent-orchestrated lab for reproducible discovery."""

from .sdk import DiscoveryLab, Experiment, PROTOCOL_VERSION
from .bundle import export_bundle, verify_bundle
from .evidence import (
    STATUSES,
    ArtifactSchema,
    BudgetExceeded,
    EvidenceError,
    EvidenceStore,
    ExperimentSpecV2,
    FieldSchema,
    MetricSpec,
    ResourceBudget,
    RunContext,
    ValidationError,
    accept_run,
    compare_runs,
    experiment,
    inspect_run,
    lineage_graph,
    list_runs,
    reject_run,
    reproduce_run,
    resume_run,
    validate_run,
)

__all__ = [
    "ArtifactSchema", "BudgetExceeded", "DiscoveryLab", "EvidenceError",
    "EvidenceStore", "Experiment", "ExperimentSpecV2", "FieldSchema",
    "MetricSpec", "PROTOCOL_VERSION", "ResourceBudget", "RunContext", "STATUSES",
    "ValidationError", "accept_run", "compare_runs", "experiment", "export_bundle",
    "inspect_run", "lineage_graph", "list_runs", "reject_run", "reproduce_run",
    "resume_run", "validate_run", "verify_bundle",
]
