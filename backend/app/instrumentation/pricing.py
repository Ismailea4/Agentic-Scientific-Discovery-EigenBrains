"""Per-model pricing used to estimate USD cost from token counts.

`DEFAULT_PRICING` starts empty. A call has no dollar estimate until challenge
code registers a price it has checked. This module does not ship list prices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PriceRecord:
    input_cost_per_1k: float
    output_cost_per_1k: float
    source: str
    checked_at: str


class PricingTable:
    def __init__(self) -> None:
        self._prices: dict[str, PriceRecord] = {}

    def register_model(
        self,
        name: str,
        input_cost_per_1k: float,
        output_cost_per_1k: float,
    ) -> None:
        """Register a price without provenance for backwards compatibility.

        Benchmark configuration should use ``register_checked_model`` or
        ``from_checked_json`` so the source and check time remain auditable.
        """
        self.register_checked_model(
            name,
            input_cost_per_1k,
            output_cost_per_1k,
            source="caller_supplied",
            checked_at="unspecified",
        )

    def register_checked_model(
        self,
        name: str,
        input_cost_per_1k: float,
        output_cost_per_1k: float,
        *,
        source: str,
        checked_at: str,
    ) -> None:
        if not name.strip() or not source.strip() or not checked_at.strip():
            raise ValueError("model, pricing source, and checked_at are required")
        if input_cost_per_1k < 0 or output_cost_per_1k < 0:
            raise ValueError("token prices must be >= 0")
        self._prices[name] = PriceRecord(
            input_cost_per_1k=float(input_cost_per_1k),
            output_cost_per_1k=float(output_cost_per_1k),
            source=source,
            checked_at=checked_at,
        )

    @classmethod
    def from_checked_json(cls, path: str | Path) -> "PricingTable":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("pricing config must contain a models list")
        table = cls()
        for row in payload["models"]:
            table.register_checked_model(
                row["model"],
                row["input_cost_per_1k"],
                row["output_cost_per_1k"],
                source=row["source"],
                checked_at=row["checked_at"],
            )
        return table

    def provenance(self, model: str) -> PriceRecord | None:
        return self._prices.get(model)

    def estimate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float | None:
        """Estimated USD cost, or None if the model has no registered price."""
        entry = self._prices.get(model)
        if entry is None:
            return None
        return (input_tokens / 1000.0) * entry.input_cost_per_1k + (
            output_tokens / 1000.0
        ) * entry.output_cost_per_1k


# Empty on purpose. Register a checked per-1k price before a demo shows cost.
DEFAULT_PRICING = PricingTable()
