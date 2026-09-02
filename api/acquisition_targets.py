"""
Acquisition target finder.

Pipeline (all in a background thread, queue-based SSE to keep connection alive):
  1. search_companies → 150 company rows (always works, no agency string issues)
  2. semantic_search → per-firm relevance scores if technology_query is provided
  3. Score + rank → top 5 candidates; check acquisition cache for each
  4. Send "company" SSE events immediately so cards appear in the UI
  5. Stream ONE Claude call (web_search tool, max_uses=5) that researches
     and synthesizes all 5 companies together

SSE event types:
  {"type": "progress", "data": {"message": "...", "current": N, "total": N}}
  {"type": "company",  "data": {...company dict...}}
  {"type": "text",     "data": "token..."}
  {"type": "done"}
"""

import json
import logging
import math
import queue
import threading
from collections import Counter
from typing import Iterator

import anthropic

from .search import semantic_search, get_db
from .models import SearchFilters

log = logging.getLogger(__name__)

CLAUDE_MODEL   = "claude-opus-5"
MAX_CANDIDATES = 5     # companies to analyze
SEMANTIC_LIMIT = 150   # award results for candidate discovery
KEEPALIVE_SECS = 5     # SSE keepalive interval


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(p2_rate: float, year_last: int, award_count: int, sem_score: float = 0.0) -> float:
    recency = max(0.0, 1.0 - (2026 - year_last) / 20.0)
    size    = min(1.0, math.log10(max(award_count, 1)) / 3.0)
    return sem_score * 40 + p2_rate * 30 + recency * 20 + size * 10


# ── Candidate discovery ───────────────────────────────────────────────────────

def _find_candidates(criteria: dict) -> list[dict]:
    """
    Use search_companies as the primary source (always returns data).
    Semantic search provides optional relevance scores to filter and rerank.
    If semantic search fails or returns nothing, all company rows are kept.
    """
    technology_query = (criteria.get("technology_query") or "").strip()
    company_profile  = criteria.get("company_profile", "either")
    sort_by          = "funding" if company_profile == "platform" else "count"

    from .companies import search_companies

    # Do NOT pass filter_agency — our UI labels don't match DB strings.
    # Agency preference is handled by semantic reranking and synthesis context.
    rows = search_companies(query="", sort_by=sort_by, filter_agency=None, limit=150)
    log.info("search_companies returned %d rows", len(rows))

    # Semantic scores (lowercase keys for robust matching)
    semantic_scores: dict[str, float] = {}
    if technology_query:
        try:
            sem_results = semantic_search(technology_query, SearchFilters(), SEMANTIC_LIMIT)
            firm_sims: dict[str, list[float]] = {}
            for r in sem_results:
                if r.firm:
                    firm_sims.setdefault(r.firm.lower().strip(), []).append(r.similarity)
            for key, sims in firm_sims.items():
                semantic_scores[key] = sum(sims) / len(sims)
            log.info("Semantic search found %d unique firms", len(semantic_scores))
        except Exception as e:
            log.warning("Semantic search error (skipping semantic filter): %s", e)

    use_sem_filter = bool(technology_query and semantic_scores)

    candidates = []
    for r in rows:
        if (r.get("award_count") or 0) < 3:
            continue
        firm     = r["firm"]
        firm_key = firm.lower().strip()

        if use_sem_filter and firm_key not in semantic_scores:
            continue

        p2_rate   = (r.get("phase_2_count") or 0) / max(r.get("award_count") or 1, 1)
        year_last = r.get("year_last") or 2020
        sem_score = semantic_scores.get(firm_key, 0.0)
        fit_score = _score(p2_rate, year_last, r.get("award_count") or 1, sem_score)

        if company_profile == "specialist":
            fit_score += p2_rate * 5
        elif company_profile == "platform":
            fit_score += min(5, math.log10(max(r.get("award_count") or 1, 1)) * 2)

        candidates.append({
            "firm":          firm,
            "state":         None,
            "award_count":   r.get("award_count", 0),
            "total_funding": r.get("total_funding", 0),
            "phase_2_count": r.get("phase_2_count", 0),
            "phase_2_rate":  round(p2_rate * 100, 1),
            "year_first":    r.get("year_first"),
            "year_last":     year_last,
            "primary_agency": None,
            "fit_score":     round(fit_score, 2),
        })

    log.info("_find_candidates returning %d candidates", len(candidates))
    return sorted(candidates, key=lambda x: x["fit_score"], reverse=True)


# ── Acquisition cache check (fast — no API call) ──────────────────────────────

def _check_cache(firm: str) -> dict | None:
    try:
        resp = (get_db().table("company_acquisition_info")
                .select("acquired,acquired_by,acquisition_year")
                .eq("firm", firm).execute())
        return resp.data[0] if resp.data else None
    except Exception as e:
        log.warning("Cache check failed for %s: %s", firm, e)
        return None


# ── Claude synthesis (web research + analysis in one streaming call) ───────────

def _format_criteria(criteria: dict) -> str:
    lines = []
    if criteria.get("domains"):
        lines.append(f"Target markets: {', '.join(criteria['domains'])}")
    if criteria.get("technology_query"):
        lines.append(f"Technology focus: {criteria['technology_query']}")
    if criteria.get("agencies"):
        lines.append(f"Preferred agency relationships: {', '.join(criteria['agencies'])}")
    profile = criteria.get("company_profile", "either")
    if profile != "either":
        lines.append(f"Company profile: {profile}")
    if criteria.get("rationale"):
        lines.append(f"Strategic rationale: {', '.join(criteria['rationale'])}")
    if criteria.get("open_criteria"):
        lines.append(f"Additional context: {criteria['open_criteria']}")
    return "\n".join(lines) if lines else "No specific criteria provided."


def _stream_synthesis(criteria: dict, companies: list[dict]) -> Iterator[str]:
    if not companies:
        yield "No active acquisition targets found matching your criteria."
        return

    criteria_text = _format_criteria(criteria)
    co_lines = []
    for c in companies:
        funding = f"${c['total_funding']:,.0f}" if c.get("total_funding") else "unknown"
        years   = f"{c.get('year_first', '?')}–{c.get('year_last', '?')}"
        co_lines.append(
            f"- **{c['firm']}**: {c['award_count']} SBIR/STTR awards, "
            f"{c['phase_2_rate']}% Phase II rate, {funding} total SBIR funding, "
            f"active {years}"
        )

    system = (
        "You are a senior M&A analyst specializing in technology acquisitions. "
        "Use web search to research each company (revenue, recent news, acquisition status), "
        "then provide strategic acquisition analysis. "
        "Format with ## headers and **bold** for key points."
    )

    prompt = (
        "## Companies to Analyze\n"
        + "\n".join(co_lines)
        + f"\n\n## Acquirer Criteria\n{criteria_text}\n\n"
        "For each company, search the web to find: current revenue or size signals "
        "(employees, annual revenue, press coverage), whether it has been recently acquired, "
        "and notable recent contracts or news.\n\n"
        "Then write:\n"
        "1. **## Landscape Assessment** — 2-3 paragraphs on overall themes, what this market "
        "segment looks like based on these SBIR portfolios, and strategic considerations.\n"
        "2. **## [Company Name]** — one section per company covering: technology fit to stated "
        "criteria, estimated revenue/size from your web search, acquisition status, strategic "
        "rationale, and key risks or integration considerations.\n\n"
        "Be specific — cite SBIR data, web search findings, and agency relationships."
    )

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for token in stream.text_stream:
            yield token


# ── Background worker ─────────────────────────────────────────────────────────

def _run_pipeline(criteria: dict, ev_queue: queue.Queue) -> None:
    def push(obj: dict):
        ev_queue.put(f"data: {json.dumps(obj)}\n\n")

    try:
        push({"type": "progress", "data": {
            "message": "Searching database for candidates…", "current": 0, "total": 0,
        }})

        try:
            candidates = _find_candidates(criteria)
        except Exception as e:
            log.error("Candidate search error: %s", e)
            push({"type": "progress", "data": {
                "message": f"Database search error: {e}", "current": 0, "total": 0,
            }})
            return

        if not candidates:
            push({"type": "progress", "data": {
                "message": "No candidates found — try broadening your technology description.",
                "current": 0, "total": 0,
            }})
            return

        top = candidates[:MAX_CANDIDATES]
        push({"type": "progress", "data": {
            "message": f"Found {len(candidates)} candidates — building company cards…",
            "current": 0, "total": len(top),
        }})

        # Check acquisition cache (fast Supabase lookups, no API call) and send cards
        active = []
        for i, c in enumerate(top):
            cache = _check_cache(c["firm"])
            already_acquired = bool(cache and cache.get("acquired"))
            enriched = {
                **c,
                "already_acquired":  already_acquired,
                "acquirer":          cache.get("acquired_by")      if cache else None,
                "acquisition_year":  cache.get("acquisition_year") if cache else None,
            }
            push({"type": "company", "data": enriched})
            if not already_acquired:
                active.append(enriched)
            push({"type": "progress", "data": {
                "message": f"Added {c['firm']}…",
                "current": i + 1, "total": len(top),
            }})

        push({"type": "progress", "data": {
            "message": "Researching companies and generating analysis…",
            "current": len(top), "total": len(top),
        }})

        # One Claude call: web research + synthesis for all active companies
        try:
            for token in _stream_synthesis(criteria, active):
                ev_queue.put(f"data: {json.dumps({'type': 'text', 'data': token})}\n\n")
        except Exception as e:
            log.error("Synthesis error: %s", e)
            ev_queue.put(
                f"data: {json.dumps({'type': 'text', 'data': f'[Analysis error: {e}]'})}\n\n"
            )

    finally:
        ev_queue.put(f"data: {json.dumps({'type': 'done'})}\n\n")
        ev_queue.put(None)


# ── Public streaming entry point ──────────────────────────────────────────────

def stream_acquisition_targets(criteria: dict) -> Iterator[str]:
    """
    Generator consumed by FastAPI StreamingResponse.
    A background thread runs the pipeline and pushes events into a queue.
    The generator reads with a short timeout, yielding SSE keepalive comments
    during silence so Render never closes the connection.
    """
    ev_queue: queue.Queue = queue.Queue()
    worker = threading.Thread(target=_run_pipeline, args=(criteria, ev_queue), daemon=True)
    worker.start()

    while True:
        try:
            item = ev_queue.get(timeout=KEEPALIVE_SECS)
            if item is None:
                break
            yield item
        except queue.Empty:
            yield ": keepalive\n\n"

    worker.join(timeout=5)
