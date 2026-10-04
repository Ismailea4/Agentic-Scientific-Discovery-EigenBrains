"""Literature access (OpenAlex and arXiv). Evidence can only be recorded for works
whose identifier resolves at its source, so a citation cannot be invented.

Every work carries deterministic credibility facts (publication type, venue
type, retraction status, citations) and a tier label, so agents and readers can
weigh a claim by its source instead of treating every hit as equal. The tiers
describe the evidence trail, not the truth of a claim.

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
FIELDS = ("id,doi,title,publication_year,primary_location,cited_by_count,authorships,abstract_inverted_index,"
          "type,is_retracted")
HIGHLY_CITED = 100
CITED = 10
PEER_REVIEWED_TYPES = {"article", "review", "conference-paper", "book-chapter", "book", "proceedings-article"}
PEER_REVIEWED_VENUES = {"journal", "conference", "book series", "ebook platform"}
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


def credibility(kind: str | None, venue_type: str | None, cited_by: int | None, retracted: bool,
                source: str = "openalex") -> dict:
    """Deterministic, explainable credibility facts for one work."""
    if retracted:
        status = "retracted"
    elif source == "arxiv" or kind == "preprint" or venue_type == "repository":
        status = "preprint (not peer-reviewed)"
    elif kind in ("report", "dissertation"):
        status = f"{kind} (not peer-reviewed)"
    elif kind in PEER_REVIEWED_TYPES and venue_type in PEER_REVIEWED_VENUES:
        status = "peer-reviewed"
    else:
        status = "venue unverified"
    if cited_by is None:
        uptake = "citations unknown"
    elif cited_by >= HIGHLY_CITED:
        uptake = "highly cited"
    elif cited_by >= CITED:
        uptake = "cited"
    else:
        uptake = "low-citation"
    return {"status": status, "uptake": uptake, "cited_by": cited_by, "type": kind, "venue_type": venue_type,
            "retracted": retracted, "label": f"{status} · {uptake}" + (f" ({cited_by})" if cited_by is not None else "")}


def _work(w: dict) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    authors = [a["author"]["display_name"] for a in (w.get("authorships") or [])[:4] if a.get("author")]
    return {
        "openalex_id": w["id"].rsplit("/", 1)[-1],
        "doi": w.get("doi"),
        "title": w.get("title"),
        "year": w.get("publication_year"),
        "venue": src.get("display_name"),
        "authors": authors,
        "cited_by": w.get("cited_by_count"),
        "credibility": credibility(w.get("type"), src.get("type"), w.get("cited_by_count"),
                                   bool(w.get("is_retracted"))),
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


def search_works(query: str, max_results: int = 6, mode: str = "relevance") -> list[dict]:
    """mode 'relevance': OpenAlex relevance ranking over full text.
    mode 'most_cited': works whose title or abstract match, most cited first (finds
    canonical anchors; results can include off-topic fields, so judge relevance)."""
    if not query.strip():
        raise ValueError("empty query")
    n = max(1, min(max_results, 15))
    if mode == "relevance":
        params = {"search": query, "per_page": n, "select": FIELDS}
    elif mode == "most_cited":
        params = {"filter": f"title_and_abstract.search:{query}", "sort": "cited_by_count:desc", "per_page": n,
                  "select": FIELDS}
    else:
        raise ValueError("mode must be 'relevance' or 'most_cited'")
    return [_work(w) for w in _get("/works", params).get("results", [])]


ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_ID = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.IGNORECASE)
_ATOM = {"a": "http://www.w3.org/2005/Atom"}


def parse_arxiv_feed(xml_text: str) -> list[dict]:
    """Parse an arXiv API Atom feed into work records (no network)."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall("a:entry", _ATOM):
        raw_id = (e.findtext("a:id", default="", namespaces=_ATOM) or "").rsplit("/abs/", 1)[-1]
        m = _ARXIV_ID.match(raw_id)
        if not m:
            continue
        text = lambda tag: " ".join((e.findtext(tag, default="", namespaces=_ATOM) or "").split())  # noqa: E731
        out.append({
            "arxiv_id": m.group(1),
            "title": text("a:title"),
            "year": int(text("a:published")[:4]) if text("a:published") else None,
            "authors": [a.findtext("a:name", default="", namespaces=_ATOM) for a in e.findall("a:author", _ATOM)][:4],
            "abstract": text("a:summary")[:1200],
            "url": f"https://arxiv.org/abs/{m.group(1)}",
            "credibility": credibility("preprint", "repository", None, False, source="arxiv"),
        })
    return out


ARXIV_MIN_INTERVAL_SEC = 3.0  # arXiv API terms of use: at most one request every 3 seconds
_last_arxiv_call = [0.0]


def _arxiv(params: dict) -> list[dict]:
    import time

    wait = ARXIV_MIN_INTERVAL_SEC - (time.monotonic() - _last_arxiv_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_arxiv_call[0] = time.monotonic()
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "discolab/0.1 (research lab prototype)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return parse_arxiv_feed(resp.read().decode("utf-8"))


def search_arxiv(query: str, max_results: int = 6) -> list[dict]:
    if not query.strip():
        raise ValueError("empty query")
    terms = " AND ".join(f"all:{w}" for w in query.split())
    return _arxiv({"search_query": terms, "max_results": max(1, min(max_results, 15))})


def fetch_arxiv(arxiv_id: str) -> dict:
    m = _ARXIV_ID.match(arxiv_id.strip())
    if not m:
        raise ValueError(f"not an arXiv id: {arxiv_id!r} (expected e.g. 2101.00001)")
    found = _arxiv({"id_list": m.group(1)})
    if not found:
        raise ValueError(f"arXiv id {m.group(1)} did not resolve")
    return found[0]


def is_arxiv_id(source_id: str) -> bool:
    return bool(_ARXIV_ID.match(source_id.strip()))


def fetch_work(openalex_id: str) -> dict:
    m = _ID.match(openalex_id.strip())
    if not m:
        raise ValueError(f"not an OpenAlex work id: {openalex_id!r} (expected W123...)")
    return _work(_get(f"/works/{m.group(1)}", {"select": FIELDS}))
