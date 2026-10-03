"""Small, legible architecture search space used before challenge release."""

from __future__ import annotations

from .models import ArchitectureNode, ArchitectureTemplate


def _chain(identifier: str, name: str, roles: tuple[str, ...], baseline: str | None = None) -> ArchitectureTemplate:
    nodes = tuple(ArchitectureNode(id=f"{role}-{index}", role=role) for index, role in enumerate(roles))
    edges = tuple((nodes[index].id, nodes[index + 1].id) for index in range(len(nodes) - 1))
    return ArchitectureTemplate(
        id=identifier,
        name=name,
        nodes=nodes,
        edges=edges,
        baseline_kind=baseline,
    )


def architecture_templates() -> tuple[ArchitectureTemplate, ...]:
    """Return seven reasoned templates, not a combinatorial graph swarm."""

    return (
        _chain("A0", "Strongest single solver", ("solver",), "single_model"),
        _chain("A1", "Solver then verifier", ("solver", "verifier")),
        ArchitectureTemplate(
            id="A2",
            name="Independent solvers then synthesizer",
            nodes=(
                ArchitectureNode("solver-a", "solver"),
                ArchitectureNode("solver-b", "solver"),
                ArchitectureNode("synthesizer", "synthesizer"),
            ),
            edges=(
                ("solver-a", "synthesizer"),
                ("solver-b", "synthesizer"),
            ),
            baseline_kind="static_multi_agent",
        ),
        _chain("A3", "Specialist, solver, verifier", ("specialist", "solver", "verifier")),
        _chain("A4", "Solver, critic, revision", ("solver", "critic", "revision")),
        ArchitectureTemplate(
            id="A5",
            name="Two solvers, disagreement detector, conditional critic",
            nodes=(
                ArchitectureNode("solver-a", "solver"),
                ArchitectureNode("solver-b", "solver"),
                ArchitectureNode("disagreement", "disagreement_detector"),
                ArchitectureNode("critic", "critic", optional=True),
            ),
            edges=(
                ("solver-a", "disagreement"),
                ("solver-b", "disagreement"),
                ("disagreement", "critic"),
            ),
            metadata={"conditional_role": "critic", "condition": "measured disagreement policy"},
        ),
        _chain("A6", "Router, task-specific solver, verifier", ("router", "task_specific_solver", "verifier")),
    )
