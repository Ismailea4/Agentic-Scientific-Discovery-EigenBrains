"""Load and sanity-check the frozen pre-registration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from .landscapes import LANDSCAPES
from .ledger import file_sha256

PREREG_PATH = Path(__file__).resolve().parent.parent / "prereg.yaml"


def load_prereg(path: str | None = None) -> dict:
    """The active pre-registration: explicit path, else $DISCOLAB_PREREG (used by
    the acceleration study's derived protocols), else prereg.yaml."""
    return _load(str(Path(path or os.environ.get("DISCOLAB_PREREG") or PREREG_PATH).resolve()))


@lru_cache(maxsize=16)
def _load(path: str) -> dict:
    p = Path(path)
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    dev = set(data["landscapes"]["development"])
    held = set(data["landscapes"]["held_out"])
    if dev & held:
        raise ValueError("development and held-out landscapes overlap")
    unknown = (dev | held) - set(LANDSCAPES)
    if unknown:
        raise ValueError(f"prereg names unknown landscapes: {unknown}")
    ids = [h["id"] for h in data["hypotheses"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate hypothesis ids in prereg")
    data["_sha256"] = file_sha256(p)
    data["_path"] = str(p)
    return data


def initial_prior(h: dict, hyps: dict[str, dict]) -> float:
    """Prior for a hypothesis, applying the pre-registered coupling rule if present."""
    rule = h.get("prior_rule")
    if not rule:
        return float(h["prior"])
    parent = hyps[rule["depends_on"]]
    q = float(parent.get("posterior", parent.get("prior")))
    return q * rule["if_true"] + (1 - q) * rule["if_false"]
