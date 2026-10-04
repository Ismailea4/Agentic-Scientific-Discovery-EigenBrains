"""OpenAlex literature access. Evidence can only be recorded for works whose
identifier resolves in OpenAlex, so a citation cannot be invented.

Set OPENALEX_API_KEY in the environment if your usage needs a key; the
module never logs or returns it.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

BASE = "https://api.openalex.org"
FIELDS = "id,doi,title,publication_year,primary_location,cited_by_count,authorships,abstract_inverted_index"
_ID = re.compile(r"^(?:https://openalex\.org/)?(W\d+)$")


def _get(path: str, params: dict) -> dict:
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params = {**params, "api_key": key}
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "discolab/0.1 (research lab prototype)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _abstract(inv: dict | None, limit: int = 1200) -> str | None:
    if not inv:
        return None
    pos = sorted((p, w) for w, ps in inv.items() for p in ps)
    text = " ".join(w for _, w in pos)
    return text[:limit] + ("..." if len(text) > limit else "")


def _work(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = (loc.get("source") or {}).get("display_name")
    authors = [a["author"]["display_name"] for a in (w.get("authorships") or [])[:4] if a.get("author")]
    return {
        "openalex_id": w["id"].rsplit("/", 1)[-1],
        "doi": w.get("doi"),
        "title": w.get("title"),
        "year": w.get("publication_year"),
        "venue": src,
        "authors": authors,
        "cited_by": w.get("cited_by_count"),
        "abstract": _abstract(w.get("abstract_inverted_index")),
    }


TITLE_MATCH_MIN = 0.6
_WORD = re.compile(r"[a-z0-9]+")


def title_similarity(a: str, b: str) -> float:
    """Jaccard similarity of lower-cased word sets (robust to case and punctuation)."""
    wa, wb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def search_works(query: str, max_results: int = 6) -> list[dict]:
    if not query.strip():
        raise ValueError("empty query")
    data = _get("/works", {"search": query, "per_page": max(1, min(max_results, 15)), "select": FIELDS})
    return [_work(w) for w in data.get("results", [])]


def fetch_work(openalex_id: str) -> dict:
    m = _ID.match(openalex_id.strip())
    if not m:
        raise ValueError(f"not an OpenAlex work id: {openalex_id!r} (expected W123...)")
    return _work(_get(f"/works/{m.group(1)}", {"select": FIELDS}))
