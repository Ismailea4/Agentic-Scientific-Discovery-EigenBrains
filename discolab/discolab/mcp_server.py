"""MCP tool server exposing the lab to Omnigent agents.

One server module serves every agent; each agent's tools/mcp/lab.yaml
allow-lists the subset it may call and sets DISCOLAB_ACTOR so every ledger
event is attributed. Run with:  python -m discolab.mcp_server
"""

from __future__ import annotations

import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

from . import lab
from .experiments import n_workers
from .features import FEATURE_SETS
from .ledger import Ledger
from .literature import TITLE_MATCH_MIN, fetch_arxiv, fetch_work, is_arxiv_id, search_arxiv, search_works, \n    title_similarity
from .prereg import load_prereg
from .views import result_summary, state_summary

mcp = FastMCP("discolab")

EXPERIMENT_TIMEOUT_SEC = 1800
EVIDENCE_RELATIONS = ("supports", "contradicts", "context", "method", "baseline")


def _actor() -> str:
    return os.environ.get("DISCOLAB_ACTOR", "unknown-agent")


@mcp.tool()
def get_research_state() -> dict:
    """Current research record: question, hypotheses with posteriors, evidence,
    candidate experiments with scores and status, compute budget, last decision."""
    return state_summary(Ledger(lab.lab_root()).state())


@mcp.tool()
def list_design_space() -> dict:
    """What experiments can be proposed: landscapes (development vs held-out),
    feature sets, controllers, seed limits, and what each hypothesis needs."""
    pr = load_prereg()
    s = Ledger(lab.lab_root()).state()
    return {
        "kinds": {
            "prediction": "Does a feature set predict stagnation onset better than fitness history? "
                          "feature_sets must include 'fitness'. Development stage = leave-one-landscape-out "
                          "over >= 2 development landscapes; confirmatory = held-out landscapes.",
            "control": "Do mutation controllers recover faster after landscape shifts? controllers must "
                       "include 'B0_fixed'; include 'B3_predictive' to test H4.",
        },
        "landscapes": pr["landscapes"],
        "feature_sets": {k: list(v) for k, v in FEATURE_SETS.items()},
        "controllers": pr["control_study"]["controllers"],
        "controller_variants": {
            "B3d_predictive": "predictive controller whose frozen risk model uses fitness+dispersion features",
            "B0_fixed_x<m>": "fixed mutation rate m/d for 0.25 <= m <= 4 (rate-matched controls, e.g. B0_fixed_x0.8)",
        },
        "n_seeds": {"min": 4, "max": 50},
        "hypotheses": {h["id"]: {"family": h["family"], "feature_set": h.get("feature_set"),
                                 "controller": h.get("controller"), "status": h["status"]}
                       for h in s["hypotheses"].values()},
        "rules": pr["planner_policy"]["hard_constraints"],
        "parallel_workers": n_workers(),
    }


@mcp.tool()
def propose_experiment(kind: str, title: str, rationale: str, hypotheses: list[str], landscapes: list[str],
                       n_seeds: int, feature_sets: list[str] | None = None,
                       controllers: list[str] | None = None) -> dict:
    """Propose one candidate experiment (validated against the pre-registration).
    kind: 'prediction' or 'control'. Returns its id, stage and simulated workload."""
    spec = {"kind": kind, "title": title, "rationale": rationale, "hypotheses": hypotheses,
            "landscapes": landscapes, "n_seeds": n_seeds, "feature_sets": feature_sets,
            "controllers": controllers}
    return lab.propose_experiment(spec, _actor())


@mcp.tool()
def score_experiments() -> dict:
    """Score every open candidate: expected information gain (bits), estimated
    compute cost, held-out penalty, utility, and hard-constraint feasibility.
    Also returns the research portfolio: up to 3 experiments chosen greedily for
    their JOINT information after redundancy (experiments testing the same
    hypothesis overlap), with each step's marginal gain."""
    out = lab.score_experiments(_actor())
    keep = ("id", "title", "kind", "stage", "eig_bits", "cost_penalty_bits", "heldout_penalty_bits",
            "utility", "feasible", "violations", "hypotheses")
    return {"argmax": out["argmax"], "portfolio": out["portfolio"],
            "scores": [{k: r[k] for k in keep} | {"est_wall_seconds": r["cost"]["wall_seconds"]}
                       for r in out["scores"]]}


@mcp.tool()
def select_experiment(experiment_id: str, justification: str) -> dict:
    """Select the experiment to run from the latest scoring round. If it is not
    the utility argmax, the justification must explain why."""
    return lab.select_experiment(experiment_id, justification, _actor())


@mcp.tool()
def run_experiment() -> dict:
    """Run the selected experiment for real (GA simulations + pre-registered
    analysis). Returns a compact result; raw artifacts are written to disk."""
    # Experiments run in an isolated worker process with explicit standard
    # handles. Spawning the process pool directly from this stdio server can
    # hang on Windows (children would implicitly inherit the MCP stdin pipe
    # while it has a pending read), and isolation keeps a crashing experiment
    # from taking the tool server down with it.
    selected = Ledger(lab.lab_root()).state()["selected"]
    proc = subprocess.run([sys.executable, "-m", "discolab.cli", "run-selected", _actor()],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=EXPERIMENT_TIMEOUT_SEC,
                          env=os.environ.copy())
    if proc.returncode != 0:
        raise RuntimeError(f"experiment {selected} failed: {proc.stderr.strip()[-1500:]}")
    cand = Ledger(lab.lab_root()).state()["candidates"][selected]
    return result_summary(cand)


@mcp.tool()
def get_experiment_result(experiment_id: str) -> dict:
    """Compact numerical result, verdicts and (if recorded) the critic's analysis."""
    s = Ledger(lab.lab_root()).state()
    if experiment_id not in s["candidates"]:
        raise ValueError(f"unknown experiment {experiment_id}")
    return result_summary(s["candidates"][experiment_id])


@mcp.tool()
def analyze_failure_dependence(experiment_id: str) -> dict:
    """For a completed CONTROL experiment: do controllers fail on the same runs?
    Uses the EigenBrains econometrics layer (covariance, Jaccard failure similarity,
    conditional failure, paired run-level bootstrap, complementary-pair selection).
    Low overlap between two controllers means they are complementary (a combined
    policy may beat both); high overlap means one adds nothing beyond the other."""
    from .portfolio import analyze

    s = Ledger(lab.lab_root()).state()
    cand = s["candidates"].get(experiment_id)
    if cand is None or cand["spec"]["kind"] != "control" or cand["status"] not in ("completed", "analyzed"):
        raise ValueError(f"{experiment_id} is not a completed control experiment")
    path = lab.lab_root() / cand["artifacts"] / "outcomes.jsonl"
    r = analyze(path, horizon=load_prereg()["control_study"]["period_generations"])
    keep = ("jaccard_failure_similarity", "p_right_fails_given_left_fails", "correlation")
    return {
        "n_runs": r["n_runs"], "mean_run_recovery": {k: round(v, 3) for k, v in r["mean_run_recovery"].items()},
        "pairs": [{"left": b["left"], "right": b["right"],
                   **{m: {"estimate": round(b["metrics"][m]["estimate"], 3),
                          "ci95": [round(b["metrics"][m]["lower"], 3), round(b["metrics"][m]["upper"], 3)]}
                      for m in keep if b["metrics"][m]["estimate"] is not None}}
                  for b in r["run_level_bootstrap"]],
        "complementary_pair": r["complementary_pair"]["pair"],
        "note": "run-level cases (independent units); a run fails when >= 3 of its 5 shifts are not recovered",
    }


@mcp.tool()
def record_analysis(experiment_id: str, interpretation: str, threats_to_validity: list[str]) -> dict:
    """Record the critic's interpretation of a completed experiment. This triggers
    the pre-registered Bayesian update of the tested hypotheses."""
    return lab.record_analysis(experiment_id, interpretation, threats_to_validity, _actor())


@mcp.tool()
def record_decision(decision: str, rationale: str, next_experiment: str | None = None) -> dict:
    """Record the next scientific decision and why (cite experiment ids and posteriors)."""
    return lab.record_decision(decision, rationale, next_experiment, _actor())


@mcp.tool()
def register_hypothesis(hypothesis_id: str, statement: str, h0: str, family: str,
                        feature_set: str | None = None, baseline_feature_set: str | None = None,
                        controller: str | None = None, comparator: str | None = None) -> dict:
    """Register a new agent-generated hypothesis (labelled origin=agent, prior 0.5). It must be
    testable as written. family 'prediction': feature_set is compared with baseline_feature_set
    (default 'fitness'); both must exist in list_design_space. family 'control': controller is
    compared with comparator ('best_baseline' by default, or a specific controller such as a
    rate-matched 'B0_fixed_x0.8')."""
    return lab.register_hypothesis(hypothesis_id, statement, h0, family, feature_set, controller, _actor(),
                                   baseline_feature_set=baseline_feature_set, comparator=comparator)


@mcp.tool()
def search_literature(query: str, max_results: int = 6, mode: str = "relevance") -> list[dict]:
    """Search OpenAlex (peer-reviewed literature across disciplines). mode 'relevance' ranks
    by match; mode 'most_cited' returns title/abstract matches most-cited first, to find
    the canonical work on a topic (judge topical relevance yourself). Each work carries
    credibility facts: peer-review status, citations, venue type, retraction."""
    return search_works(query, max_results, mode)


@mcp.tool()
def search_arxiv_papers(query: str, max_results: int = 6) -> list[dict]:
    """Search arXiv (preprints in AI, optimisation, evolutionary computation). Returns
    arxiv_id, title, year, authors, abstract. Throttled to arXiv's 1 request / 3 s."""
    return search_arxiv(query, max_results)


@mcp.tool()
def record_evidence(source_id: str, cited_title: str, claim: str, relation: str, limitation: str,
                    hypothesis_id: str | None = None) -> dict:
    """Record literature evidence from OpenAlex (source_id 'W...') or arXiv (e.g.
    '2101.00001'). The record is re-fetched from its source and its title must match
    cited_title (the title you read in the search results), so a mistyped id that points
    at a different paper is rejected. The claim must be what the source's abstract
    actually supports. limitation: the source's main limitation for this claim (design,
    system studied, comparator, size) — required, as in an evidence map. Retracted works
    are refused. relation: supports | contradicts | context | method | baseline."""
    if not limitation.strip():
        raise ValueError("state the source's main limitation for this claim")
    if relation not in EVIDENCE_RELATIONS:
        raise ValueError(f"relation must be one of {EVIDENCE_RELATIONS}")
    if is_arxiv_id(source_id):
        w = fetch_arxiv(source_id)
        ids = {"arxiv_id": w["arxiv_id"], "url": w["url"]}
    else:
        w = fetch_work(source_id)
        ids = {"openalex_id": w["openalex_id"], "doi": w["doi"], "venue": w["venue"]}
    if title_similarity(cited_title, w["title"] or "") < TITLE_MATCH_MIN:
        raise ValueError(f"{source_id} is titled {w['title']!r}, which does not match the cited title "
                         f"{cited_title!r}; check the id")
    if w["credibility"]["retracted"]:
        raise ValueError(f"{source_id} is retracted and cannot be used as evidence")
    payload = {**ids, "title": w["title"], "year": w["year"], "authors": w["authors"], "claim": claim,
               "claim_origin": "agent summary", "relation": relation, "hypothesis_id": hypothesis_id,
               "limitation": limitation, "credibility": w["credibility"],
               "source_excerpt": (w["abstract"] or "")[:600]}
    Ledger(lab.lab_root()).append("evidence_recorded", payload, _actor())
    return {"recorded": ids.get("openalex_id") or ids.get("arxiv_id"), "title": w["title"], "year": w["year"],
            "credibility": w["credibility"]["label"]}


if __name__ == "__main__":
    mcp.run()
