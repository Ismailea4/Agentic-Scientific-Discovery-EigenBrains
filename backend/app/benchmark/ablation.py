"""Generate understandable component removals and compare measured outcomes."""

from __future__ import annotations

from collections.abc import Iterable

from .models import AblationResult, ArchitectureBenchmarkResult, ArchitectureNode, ArchitectureTemplate

ABLATION_ROLES = ("retriever", "critic", "verifier", "specialist")


def ablation_variants(
    architecture: ArchitectureTemplate,
    *,
    direct_model_id: str = "direct-strongest-model",
) -> tuple[ArchitectureTemplate, ...]:
    variants: list[ArchitectureTemplate] = []
    for role in ABLATION_ROLES:
        if role in architecture.roles:
            variants.append(architecture.without_roles({role}, suffix=f"minus_{role}"))
    variants.append(
        ArchitectureTemplate(
            id=direct_model_id,
            name="Direct strongest model",
            nodes=(ArchitectureNode("solver", "solver"),),
            edges=(),
            baseline_kind="single_model",
            metadata={"comparison_for": architecture.id},
        )
    )
    return tuple(variants)


def compare_ablations(
    full: ArchitectureBenchmarkResult,
    variants: Iterable[ArchitectureBenchmarkResult],
    *,
    minimum_quality_effect: float,
    minimum_failure_effect: float,
) -> list[AblationResult]:
    """Compare measured variants; thresholds are supplied by the experiment."""

    if minimum_quality_effect < 0 or minimum_failure_effect < 0:
        raise ValueError("ablation effect thresholds must be >= 0")
    output: list[AblationResult] = []
    for variant in variants:
        removed = tuple(variant.metadata.get("removed_roles", ()))
        quality_loss = full.expected_quality - variant.expected_quality
        failure_increase = variant.failure_rate - full.failure_rate
        necessary = quality_loss >= minimum_quality_effect or failure_increase >= minimum_failure_effect
        note = (
            "component removal caused a measured degradation"
            if necessary
            else "no degradation exceeded the declared experimental threshold"
        )
        output.append(
            AblationResult(
                architecture_id=full.architecture_id,
                variant_id=variant.architecture_id,
                removed_roles=removed,
                quality_delta=variant.expected_quality - full.expected_quality,
                cost_delta=(variant.cost - full.cost) if variant.cost is not None and full.cost is not None else None,
                latency_delta=variant.latency - full.latency,
                failure_rate_delta=variant.failure_rate - full.failure_rate,
                component_necessary=necessary,
                evidence_note=note,
            )
        )
    return output
