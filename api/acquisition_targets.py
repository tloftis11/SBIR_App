"""
Acquisition target finder.

Pipeline (background thread → queue → SSE generator with keepalives):
  1. search_companies (filter_year_min=2023) + semantic reranking
  2. Quick acquisition-cache check per candidate
  3. Send company cards immediately
  4. Fetch recent awards per company for context
  5. ONE blocking Claude call with web_search (handles multi-turn internally)
  6. Replay complete text as chunked SSE tokens

SSE event types:
  {"type": "progress", "data": {"message": "...", "current": N, "total": N}}
  {"type": "company",  "data": {...}}
  {"type": "text",     "data": "chunk..."}
  {"type": "done"}
"""

import json
import logging
import math
import queue
import threading
from typing import Iterator

import anthropic

from .search import semantic_search, get_db
from .models import SearchFilters

log = logging.getLogger(__name__)

CLAUDE_MODEL   = "claude-opus-5"
MAX_CANDIDATES = 5
SEMANTIC_LIMIT = 150
KEEPALIVE_SECS = 5
YEAR_CUTOFF    = 2023   # only consider companies active since this year


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(p2_rate: float, year_last: int, award_count: int, sem: float = 0.0) -> float:
    recency = max(0.0, 1.0 - (2026 - year_last) / 10.0)
    size    = min(1.0, math.log10(max(award_count, 1)) / 3.0)
    return sem * 40 + p2_rate * 30 + recency * 20 + size * 10


# ── Candidate discovery ───────────────────────────────────────────────────────

def _find_candidates(criteria: dict) -> list[dict]:
    technology_query = (criteria.get("technology_query") or "").strip()
    company_profile  = criteria.get("company_profile", "either")
    sort_by          = "funding" if company_profile == "platform" else "count"

    from .companies import search_companies

    # filter_year_min limits to companies active since YEAR_CUTOFF.
    # Do NOT pass filter_agency — UI labels don't match DB strings.
    rows = search_companies(
        query="", sort_by=sort_by, filter_agency=None,
        filter_year_min=YEAR_CUTOFF, limit=150,
    )
    log.info("search_companies (year>=%d) returned %d rows", YEAR_CUTOFF, len(rows))

    # Semantic scores (also limited to recent awards, lowercase keys)
    semantic_scores: dict[str, float] = {}
    if technology_query:
        try:
            sem = semantic_search(
                technology_query,
                SearchFilters(year_min=YEAR_CUTOFF),
                SEMANTIC_LIMIT,
            )
            firm_sims: dict[str, list[float]] = {}
            for r in sem:
                if r.firm:
                    firm_sims.setdefault(r.firm.lower().strip(), []).append(r.similarity)
            for k, sims in firm_sims.items():
                semantic_scores[k] = sum(sims) / len(sims)
            log.info("Semantic search: %d unique firms", len(semantic_scores))
        except Exception as e:
            log.warning("Semantic search error (skipping filter): %s", e)

    use_sem = bool(technology_query and semantic_scores)

    candidates = []
    for r in rows:
        if (r.get("award_count") or 0) < 2:
            continue
        firm     = r["firm"]
        firm_key = firm.lower().strip()

        if use_sem and firm_key not in semantic_scores:
            continue

        p2_rate   = (r.get("phase_2_count") or 0) / max(r.get("award_count") or 1, 1)
        year_last = r.get("year_last") or YEAR_CUTOFF
        sem_score = semantic_scores.get(firm_key, 0.0)
        fit_score = _score(p2_rate, year_last, r.get("award_count") or 1, sem_score)

        if company_profile == "specialist":
            fit_score += p2_rate * 5
        elif company_profile == "platform":
            fit_score += min(5, math.log10(max(r.get("award_count") or 1, 1)) * 2)

        candidates.append({
            "firm":           firm,
            "state":          None,
            "award_count":    r.get("award_count", 0),
            "total_funding":  r.get("total_funding", 0),
            "phase_2_count":  r.get("phase_2_count", 0),
            "phase_2_rate":   round(p2_rate * 100, 1),
            "year_first":     r.get("year_first"),
            "year_last":      year_last,
            "primary_agency": None,
            "fit_score":      round(fit_score, 2),
        })

    log.info("_find_candidates: %d candidates", len(candidates))
    return sorted(candidates, key=lambda x: x["fit_score"], reverse=True)


# ── Acquisition cache (fast DB lookup, no API) ────────────────────────────────

def _check_cache(firm: str) -> dict | None:
    try:
        resp = (get_db().table("company_acquisition_info")
                .select("acquired,acquired_by,acquisition_year")
                .eq("firm", firm).execute())
        return resp.data[0] if resp.data else None
    except Exception as e:
        log.warning("Cache check failed for %s: %s", firm, e)
        return None


# ── Synthesis (blocking call with web search, then chunked replay) ─────────────

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
        lines.append(f"Company profile preference: {profile}")
    if criteria.get("rationale"):
        lines.append(f"Strategic rationale: {', '.join(criteria['rationale'])}")
    if criteria.get("open_criteria"):
        lines.append(f"Additional context: {criteria['open_criteria']}")
    return "\n".join(lines) if lines else "No specific criteria provided."


def _company_block(c: dict) -> str:
    funding = f"${c['total_funding']:,.0f}" if c.get("total_funding") else "unknown"
    years   = f"{c.get('year_first', '?')}–{c.get('year_last', '?')}"
    lines   = [
        f"**{c['firm']}**",
        f"  SBIR portfolio (since {YEAR_CUTOFF}): {c['award_count']} awards, "
        f"{c['phase_2_rate']}% Phase II rate, {funding} total funding, active {years}",
    ]
    for a in c.get("_awards", [])[:8]:
        meta = " | ".join(filter(None, [
            a.get("agency"), a.get("phase"),
            str(a["award_year"]) if a.get("award_year") else None,
            f"${a['award_amount']:,}" if a.get("award_amount") else None,
        ]))
        title = (a.get("title") or "Untitled")[:120]
        lines.append(f"  - {title} [{meta}]")
    return "\n".join(lines)


def _do_synthesis(criteria: dict, companies: list[dict]) -> str:
    """
    Single blocking Claude call with web_search tool.
    Returns the complete analysis text.
    The caller chunks it into SSE events while keepalives fire in parallel.
    """
    if not companies:
        return "No active acquisition targets found matching your criteria."

    criteria_text   = _format_criteria(criteria)
    companies_block = "\n\n".join(_company_block(c) for c in companies)

    system = (
        "You are a senior M&A analyst specializing in technology acquisitions. "
        "You have been given SBIR portfolio data for candidate companies. "
        "Use web search to find each company's current revenue/size signals, "
        "recent contracts or news, and whether they have been acquired. "
        "Then write a detailed strategic acquisition analysis. "
        "Use markdown: ## for section headers, **bold** for key points."
    )

    prompt = (
        f"## Candidate Companies (SBIR data since {YEAR_CUTOFF})\n\n"
        f"{companies_block}\n\n"
        f"## Acquirer Criteria\n{criteria_text}\n\n"
        "Use web search to research each company above — look for: current annual revenue "
        "or company size signals, whether the company has been acquired recently, and "
        "any notable recent contracts or news.\n\n"
        "Then write a full strategic acquisition analysis with these sections:\n"
        "## Landscape Assessment\n"
        "2-3 paragraphs on overall technology themes, what this market segment looks like, "
        "and key strategic considerations for the acquirer.\n\n"
        "## [Company Name] (one section per company)\n"
        "For each: technology fit to stated criteria, revenue and size estimate based on "
        "web search, acquisition status, strategic rationale tied to stated goals, "
        "key risks or integration considerations.\n\n"
        "Be specific and analytical — cite SBIR award data and web search findings."
    )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
    except Exception as e:
        log.error("Synthesis error: %s", e)
        return f"Analysis error: {e}"


# ── Background worker ─────────────────────────────────────────────────────────

def _run_pipeline(criteria: dict, ev_queue: queue.Queue) -> None:
    from .companies import get_company_awards

    def push(obj: dict):
        ev_queue.put(f"data: {json.dumps(obj)}\n\n")

    try:
        push({"type": "progress", "data": {
            "message": "Searching database for recent candidates…",
            "current": 0, "total": 4, "step": 1,
        }})

        try:
            candidates = _find_candidates(criteria)
        except Exception as e:
            log.error("Candidate search error: %s", e)
            push({"type": "progress", "data": {
                "message": f"Database search error: {e}",
                "current": 0, "total": 4, "step": 1,
            }})
            return

        if not candidates:
            push({"type": "progress", "data": {
                "message": (
                    "No candidates found. "
                    "All top companies may lack recent (2023+) activity, or your technology "
                    "description did not match any awards. Try broader terms."
                ),
                "current": 0, "total": 4, "step": 1,
            }})
            return

        top = candidates[:MAX_CANDIDATES]

        push({"type": "progress", "data": {
            "message": f"Found {len(candidates)} matches — loading company cards…",
            "current": 1, "total": 4, "step": 2,
        }})

        # Acquisition cache check + send cards immediately
        active = []
        for c in top:
            cache           = _check_cache(c["firm"])
            already_acquired = bool(cache and cache.get("acquired"))
            enriched = {
                **c,
                "already_acquired": already_acquired,
                "acquirer":         cache.get("acquired_by")      if cache else None,
                "acquisition_year": cache.get("acquisition_year") if cache else None,
            }
            push({"type": "company", "data": enriched})
            if not already_acquired:
                active.append(enriched)

        push({"type": "progress", "data": {
            "message": "Fetching recent award portfolios…",
            "current": 2, "total": 4, "step": 3,
        }})

        # Attach recent awards for synthesis context
        for c in active:
            try:
                awards = get_company_awards(c["firm"])
                recent = sorted(
                    [a for a in awards if (a.get("award_year") or 0) >= YEAR_CUTOFF],
                    key=lambda a: a.get("award_year") or 0, reverse=True,
                )
                c["_awards"] = recent[:10]
            except Exception as e:
                log.warning("Could not fetch awards for %s: %s", c["firm"], e)
                c["_awards"] = []

        push({"type": "progress", "data": {
            "message": "Researching companies online and writing analysis…",
            "current": 3, "total": 4, "step": 4,
        }})

        # Blocking synthesis (web search happens here, keepalives fire meanwhile)
        text = _do_synthesis(criteria, active)

        # Replay complete text as small chunks for streaming effect
        chunk_size = 80
        for i in range(0, len(text), chunk_size):
            ev_queue.put(
                f"data: {json.dumps({'type': 'text', 'data': text[i:i + chunk_size]})}\n\n"
            )

    finally:
        ev_queue.put(f"data: {json.dumps({'type': 'done'})}\n\n")
        ev_queue.put(None)


# ── Public streaming entry point ──────────────────────────────────────────────

def stream_acquisition_targets(criteria: dict) -> Iterator[str]:
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
