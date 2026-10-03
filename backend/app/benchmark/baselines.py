"""Required baseline mapping over measured architecture results."""

from __future__ import annotations

from collections.abc import Sequence

from .models import ArchitectureBenchmarkResult


def identify_baselines(
    results: Sequence[ArchitectureBenchmarkResult],
    *,
    single_id: str = "A0",
    static_id: str = "A2",
    adaptive_id: str = "A6",
) -> dict[str, str | None]:
    by_id = {result.architecture_id: result for result in results}
    viable = [result for result in results if result.cost is not None]
    cheapest = min(viable, key=lambda result: (float(result.cost), -result.expected_quality, result.architecture_id)) if viable else None
    maximum_quality = max(
        results,
        key=lambda result: (
            result.expected_quality,
            -(result.cost if result.cost is not None else float("inf")),
            result.architecture_id,
        ),
        default=None,
    )
    return {
        "B0_strongest_single": single_id if single_id in by_id else None,
        "B1_static_multi_agent": static_id if static_id in by_id else None,
        "B2_adaptive_eigenbrains": adaptive_id if adaptive_id in by_id else None,
        "B3_cheapest_viable": cheapest.architecture_id if cheapest else None,
        "B4_maximum_quality": maximum_quality.architecture_id if maximum_quality else None,
    }
