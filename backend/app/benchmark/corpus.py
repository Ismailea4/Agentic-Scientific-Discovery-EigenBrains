"""Deterministic 72-case objective corpus for Architecture Baseline v0."""

from __future__ import annotations

from .models import BenchmarkCase

CORPUS_VERSION = "pre-challenge-architecture-baseline-v0"


def _split(index: int) -> str:
    return "dev" if index < 4 else "tuning" if index == 4 else "held_out"


def _case(
    task_type: str,
    index: int,
    input_text: str,
    expected: object,
    *,
    difficulty: str = "medium",
    risk: str = "medium",
    evaluator: str = "scoring_v1",
    capabilities: tuple[str, ...] = (),
    metadata: dict | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=f"{_split(index)}-{task_type}-{index + 1:02d}",
        task_type=task_type,
        input=input_text,
        expected_answer=expected,
        evaluator=evaluator,
        difficulty=difficulty,
        risk_level=risk,
        required_capabilities=capabilities,
        metadata={"corpus_version": CORPUS_VERSION, **(metadata or {})},
        split=_split(index),
    )


def build_generic_prior_v0() -> tuple[BenchmarkCase, ...]:
    cases: list[BenchmarkCase] = []

    for index in range(6):
        incident = f"R-{20 + index}"
        severity = ("low", "medium", "high")[index % 3]
        cases.append(
            _case(
                "structured_extraction",
                index,
                f"Return JSON with incident_id and severity: Incident {incident}; severity {severity}.",
                {"incident_id": incident, "severity": severity},
                evaluator="json_exact",
                difficulty="easy",
                risk="low",
            )
        )

    for index in range(6):
        present = index % 2 == 0
        cases.append(
            _case(
                "classification",
                index,
                "Return allow or deny. The mandatory capability is "
                + ("present and not denied." if present else "absent from the grant."),
                "allow" if present else "deny",
                difficulty="easy",
                risk="high",
            )
        )

    numerical = ((2400, 600, 3), (1200, 300, 3), (900, 300, 4), (3600, 400, 4), (1500, 500, 5), (4200, 600, 6))
    for index, (input_tokens, output_tokens, calls) in enumerate(numerical):
        cases.append(
            _case(
                "numerical_reasoning",
                index,
                f"{input_tokens} input plus {output_tokens} output tokens were used over {calls} equal calls. Return total tokens per call.",
                str((input_tokens + output_tokens) // calls),
                difficulty="easy",
                risk="low",
            )
        )

    equations = ((3, 7, 28, 7), (4, 2, 22, 5), (5, -5, 30, 7), (2, 9, 25, 8), (6, 0, 54, 9), (7, 1, 50, 7))
    for index, (coefficient, offset, total, answer) in enumerate(equations):
        sign = "+" if offset >= 0 else "-"
        cases.append(
            _case(
                "mathematical_reasoning",
                index,
                f"Solve {coefficient}x {sign} {abs(offset)} = {total}. Return only x.",
                str(answer),
                difficulty="medium",
                risk="low",
            )
        )

    for index in range(6):
        predicate = ("verified", "approved", "safe", "eligible", "cached", "complete")[index]
        evidence = ("evidence", "authorization", "passed checks", "required grant", "matching hash", "all fields")[index]
        cases.append(
            _case(
                "logical_reasoning",
                index,
                f"All {predicate} items have {evidence}. This item lacks {evidence}. Is it {predicate}? Return yes, no, or undetermined.",
                "no",
                difficulty="medium",
                risk="medium",
            )
        )

    plans = (
        ("pilot,projection,full", "pilot before projection; projection before full"),
        ("measure,compare,select", "measure before compare; compare before select"),
        ("authorize,call,record", "authorize before call; call before record"),
        ("dev,tuning,held_out", "dev before tuning; tuning before held_out"),
        ("score,bounds,frontier", "score before bounds; bounds before frontier"),
        ("detect,verify,answer", "detect before verify; verify before answer"),
    )
    for index, (expected, constraints) in enumerate(plans):
        cases.append(
            _case(
                "planning",
                index,
                f"Return the only valid comma-separated order satisfying: {constraints}.",
                expected,
                difficulty="medium",
                risk="medium",
            )
        )

    for index in range(6):
        supported = index % 2 == 0
        metric = ("latency", "cost", "quality", "failure rate", "coverage", "token count")[index]
        evidence = f"Evidence explicitly reports {metric}=10." if supported else f"Evidence contains no {metric} measurement."
        cases.append(
            _case(
                "evidence_verification",
                index,
                f"{evidence} Is the claim '{metric} is measured' supported? Return supported or insufficient_evidence.",
                "supported" if supported else "insufficient_evidence",
                difficulty="medium",
                risk="high",
                metadata={"should_abstain": not supported},
            )
        )

    critique_rows = (
        ("A won one extraction case, therefore A is best everywhere.", "overgeneralization"),
        ("A and B correlate, therefore A causes B's failures.", "causal_inference"),
        ("Unknown model price is recorded as zero.", "missing_data_as_zero"),
        ("Held-out results are used to choose the routing threshold.", "held_out_contamination"),
        ("A 429 response means the credential is invalid.", "status_misclassification"),
        ("Quality gains compensate for a denied capability.", "hard_constraint_violation"),
    )
    for index, (claim, flaw) in enumerate(critique_rows):
        cases.append(_case("critique", index, f"Return only the flaw label: {claim}", flaw, risk="high"))

    for index in range(6):
        policy = "deny" if index % 2 == 0 else "allow"
        solver_a = "allow"
        solver_b = "deny"
        cases.append(
            _case(
                "synthesis",
                index,
                f"Solver A={solver_a}; solver B={solver_b}; mandatory policy={policy}. Return only the policy-consistent decision.",
                policy,
                difficulty="medium",
                risk="high",
            )
        )

    tools = (
        ("exact multiplication of supplied integers", "calculator", "calculator"),
        ("retrieve a record from the project database", "database", "database"),
        ("find current external documentation", "web_search", "network"),
        ("parse a local JSON object", "local_parser", "read"),
        ("execute deterministic unit tests", "test_runner", "execute"),
        ("inspect an attached image", "image_viewer", "read"),
    )
    for index, (task, tool, capability) in enumerate(tools):
        cases.append(
            _case(
                "tool_use_reasoning",
                index,
                f"Select the single appropriate tool for {task}. Return only the tool name.",
                tool,
                difficulty="easy",
                risk="medium",
                capabilities=(capability,),
            )
        )

    code_rows = (
        ("values=[1,2,3]; print(values[3])", "IndexError"),
        ("mapping={}; print(mapping['x'])", "KeyError"),
        ("int('not-a-number')", "ValueError"),
        ("1 / 0", "ZeroDivisionError"),
        ("open('definitely-missing.file')", "FileNotFoundError"),
        ("None + 1", "TypeError"),
    )
    for index, (code, error) in enumerate(code_rows):
        cases.append(
            _case(
                "code_understanding_debugging",
                index,
                f"Python: {code}. Return only the exception class.",
                error,
                difficulty="medium",
                risk="low",
            )
        )

    for index in range(6):
        evidence_available = index % 3 == 0
        input_text = (
            "Evidence reports failure_rate=0.12. Return only 0.12."
            if evidence_available
            else "No measurement is provided. Return only INSUFFICIENT_EVIDENCE."
        )
        cases.append(
            _case(
                "uncertainty_abstention",
                index,
                input_text,
                "0.12" if evidence_available else "INSUFFICIENT_EVIDENCE",
                difficulty="hard",
                risk="high",
                metadata={"should_abstain": not evidence_available},
            )
        )

    if len(cases) != 72 or len({case.id for case in cases}) != 72:
        raise AssertionError("baseline corpus construction must yield 72 unique cases")
    return tuple(cases)
