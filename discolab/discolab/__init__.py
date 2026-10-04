"""discolab: an Omnigent-orchestrated lab for reproducible discovery."""

from .sdk import DiscoveryLab, Experiment, PROTOCOL_VERSION
from .evidence import (
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
    reproduce_run,
    validate_run,
)

__all__ = [
    "ArtifactSchema", "BudgetExceeded", "DiscoveryLab", "EvidenceError",
    "EvidenceStore", "Experiment", "ExperimentSpecV2", "FieldSchema",
    "MetricSpec", "PROTOCOL_VERSION", "ResourceBudget", "RunContext",
    "ValidationError", "accept_run", "compare_runs", "experiment",
    "inspect_run", "reproduce_run", "validate_run",
]
