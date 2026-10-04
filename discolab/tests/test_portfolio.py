"""Failure-dependence analysis delegates to the EigenBrains covariance module."""
import json

from discolab.portfolio import analyze


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_identical_failures_overlap_and_disjoint_failures_do_not(tmp_path):
    rows = []
    for seed in range(8):
        fail_a = seed % 2 == 0
        for ctrl, fail in (("A", fail_a), ("A_copy", fail_a), ("B", not fail_a)):
            rec = [not fail] * 5
            rows.append({"landscape": "rastrigin", "seed": seed, "controller": ctrl, "recovered": rec,
                         "recovery_gens": [10 if r else 60 for r in rec], "recovery_rate": 1.0 if not fail else 0.0})
    p = tmp_path / "outcomes.jsonl"
    _write(p, rows)
    r = analyze(p, resamples=200)
    by_pair = {(x["left"], x["right"]): x for x in r["run_level"]}
    assert by_pair[("A", "A_copy")]["jaccard_similarity"] == 1.0
    assert by_pair[("A", "B")]["jaccard_similarity"] == 0.0
    assert r["n_runs"] == 8 and r["n_shifts"] == 40
    assert sorted(r["complementary_pair"]["pair"]) in (["A", "B"], ["A_copy", "B"])
