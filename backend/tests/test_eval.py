import asyncio
import csv
import json

from app.eval.framework import EvalCase, EvalRecorder, run_evaluation


def _echo(value: str) -> str:
    return value


def test_run_evaluation_produces_results_with_optional_scoring():
    cases = [
        EvalCase(case_id="c1", input="alpha", expected="alpha"),
        EvalCase(case_id="c2", input="beta", expected="beta", metadata={"lang": "en"}),
    ]

    def scorer(case, actual):
        return (1.0 if actual == case.expected else 0.0, actual == case.expected)

    results = asyncio.run(run_evaluation(cases, _echo, scorer=scorer))

    assert [r.case_id for r in results] == ["c1", "c2"]
    assert all(r.actual == r.expected for r in results)
    assert all(r.score == 1.0 and r.passed for r in results)
    assert all(r.latency_ms >= 0 for r in results)
    assert all(r.timestamp for r in results)
    assert results[1].metadata == {"lang": "en"}


def test_run_evaluation_supports_async_fn_without_scorer():
    async def async_echo(value: str) -> str:
        return value

    cases = [EvalCase(case_id="c1", input="x", expected="x")]
    results = asyncio.run(run_evaluation(cases, async_echo))
    assert results[0].actual == "x"
    assert results[0].score is None
    assert results[0].passed is None


def test_eval_recorder_writes_jsonl_and_csv_roundtrip(tmp_path):
    cases = [
        EvalCase(case_id="c1", input="alpha", expected="alpha"),
        EvalCase(case_id="c2", input="beta", expected="beta", metadata={"lang": "en"}),
    ]
    results = asyncio.run(run_evaluation(cases, _echo))

    recorder = EvalRecorder(tmp_path)
    jsonl_path = recorder.write_jsonl(results, "echo-run")
    csv_path = recorder.write_csv(results, "echo-run")

    jsonl_rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["case_id"] for row in jsonl_rows] == ["c1", "c2"]
    assert [row["actual"] for row in jsonl_rows] == ["alpha", "beta"]

    with csv_path.open(encoding="utf-8", newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    assert [row["case_id"] for row in csv_rows] == ["c1", "c2"]
    assert [json.loads(row["actual"]) for row in csv_rows] == ["alpha", "beta"]
    assert json.loads(csv_rows[1]["metadata"]) == {"lang": "en"}
