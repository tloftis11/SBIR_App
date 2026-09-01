"""
Acquisition target finder: multi-step pipeline.

SSE event types:
  {"type": "progress", "data": {"message": "...", "current": N, "total": N}}
  {"type": "text",     "data": "token..."}   — Claude synthesis tokens
  {"type": "targets",  "data": [...]}        — top 5 company dicts
  {"type": "acquired", "data": [...]}        — already-acquired companies
  {"type": "done"}
"""

import json
import logging
import math
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterator

import anthropic

from .search import get_db, semantic_search
from .models import SearchFilters

log = logging.getLogger(__name__)

RESEARCH_MODEL  = "claude-sonnet-5"
SYNTHESIS_MODEL = "claude-opus-5"
MAX_RESEARCH    = 12   # companies researched per run
MAX_WORKERS     = 6    # parallel web-search threads
TOP_N           = 5    # targets returned to UI


# ── Candidate discovery ───────────────────────────────────────────────────────

def _score(p2_rate: float, year_last: int, award_count: int, sem_score: float = 0.0) -> float:
    recency = max(0.0, 1.0 - (2026 - year_last) / 20.0)
    size    = min(1.0, math.log10(max(award_count, 1)) / 3.0)
    return sem_score * 40 + p2_rate * 30 + recency * 20 + size * 10


def _find_candidates(criteria: dict) -> list[dict]:
    technology_query  = (criteria.get("technology_query") or "").strip()
    selected_agencies = set(criteria.get("agencies") or [])
    company_profile   = criteria.get("company_profile", "either")

    if technology_query:
        # Semantic search → group by firm
        results = semantic_search(technology_query, SearchFilters(), 300)

        firms: dict[str, dict] = {}
        for r in results:
            if not r.firm:
                continue
            d = firms.setdefault(r.firm, {
                "award_count": 0, "total_funding": 0,
                "phase_2_count": 0, "year_first": 9999, "year_last": 0,
                "agencies": [], "states": [], "sim_sum": 0.0,
            })
            d["award_count"]   += 1
            d["total_funding"] += r.award_amount or 0
            if r.phase and "II" in r.phase and "III" not in r.phase:
                d["phase_2_count"] += 1
            if r.award_year:
                d["year_first"] = min(d["year_first"], r.award_year)
                d["year_last"]  = max(d["year_last"],  r.award_year)
            if r.agency:
                d["agencies"].append(r.agency)
            if r.state_code:
                d["states"].append(r.state_code)
            d["sim_sum"] += r.similarity

        candidates = []
        for firm, d in firms.items():
            if d["award_count"] < 2:
                continue
            primary_agency = Counter(d["agencies"]).most_common(1)[0][0] if d["agencies"] else None
            state          = Counter(d["states"]).most_common(1)[0][0]   if d["states"]   else None

            # Agency filter (soft: skip only if completely outside selected agencies)
            if selected_agencies and primary_agency not in selected_agencies:
                if not any(a in selected_agencies for a in d["agencies"]):
                    continue

            p2_rate    = d["phase_2_count"] / d["award_count"]
            sem_score  = d["sim_sum"] / d["award_count"]
            year_last  = d["year_last"] if d["year_last"] > 0 else 2020
            fit_score  = _score(p2_rate, year_last, d["award_count"], sem_score)

            # Profile modifier
            if company_profile == "specialist":
                fit_score += p2_rate * 5
            elif company_profile == "platform":
                fit_score += min(5, math.log10(max(d["award_count"], 1)) * 2)

            candidates.append({
                "firm":          firm,
                "state":         state,
                "award_count":   d["award_count"],
                "total_funding": d["total_funding"],
                "phase_2_count": d["phase_2_count"],
                "phase_2_rate":  round(p2_rate * 100, 1),
                "year_first":    d["year_first"] if d["year_first"] < 9999 else None,
                "year_last":     year_last,
                "primary_agency": primary_agency,
                "fit_score":     round(fit_score, 2),
            })

        return sorted(candidates, key=lambda x: x["fit_score"], reverse=True)

    else:
        # No technology query → use search_companies RPC
        from .companies import search_companies
        filter_agency = next(iter(selected_agencies), None) if len(selected_agencies) == 1 else None
        sort_by = "funding" if company_profile == "platform" else "count"
        rows = search_companies(query="", sort_by=sort_by, filter_agency=filter_agency, limit=80)

        candidates = []
        for r in rows:
            if (r.get("award_count") or 0) < 3:
                continue
            p2_rate   = (r.get("phase_2_count") or 0) / max(r.get("award_count") or 1, 1)
            year_last = (r.get("year_last") or 2020)
            fit_score = _score(p2_rate, year_last, r.get("award_count") or 1)
            candidates.append({
                "firm":           r["firm"],
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

        return sorted(candidates, key=lambda x: x["fit_score"], reverse=True)


# ── Per-company web research ──────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _research_company(company: dict, criteria: dict) -> dict:
    firm          = company["firm"]
    state         = company.get("state") or ""
    primary_agency = company.get("primary_agency") or ""

    ctx_parts = []
    if primary_agency:
        ctx_parts.append(f"primarily funded by {primary_agency}")
    if state:
        ctx_parts.append(f"based in {state}")
    context = (", " + ", ".join(ctx_parts)) if ctx_parts else ""

    prompt = (
        f'Search for current information about "{firm}", a US defense/technology company'
        f'{context} with {company["award_count"]} federal SBIR/STTR awards.\n\n'
        "Find:\n"
        "1. Revenue or size (annual revenue, employee count, or contract totals mentioned in news/press)\n"
        "2. Has this company been acquired? If yes, by whom and when?\n"
        "3. Most notable recent activity (contracts, partnerships, funding rounds, news)\n\n"
        "Return ONLY valid JSON — no other text:\n"
        "{\n"
        '  "revenue_estimate": "e.g. \'$5-15M\', \'~$50M annual\', or \'unknown\'",\n'
        '  "employee_count": integer or null,\n'
        '  "already_acquired": true or false,\n'
        '  "acquirer": "Company Name" or null,\n'
        '  "acquisition_year": year integer or null,\n'
        '  "recent_news": "1-2 sentences on most notable recent activity",\n'
        '  "web_confidence": "high", "medium", or "low"\n'
        "}"
    )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=RESEARCH_MODEL,
            max_tokens=512,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        parsed = _extract_json(text)
        if parsed:
            return {**company, **parsed}
    except Exception as e:
        log.warning("Research failed for %s: %s", firm, e)

    return {
        **company,
        "revenue_estimate":  "unknown",
        "employee_count":    None,
        "already_acquired":  False,
        "acquirer":          None,
        "acquisition_year":  None,
        "recent_news":       "No information found.",
        "web_confidence":    "low",
    }


# ── Claude synthesis ──────────────────────────────────────────────────────────

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


def _format_company_for_synthesis(c: dict) -> str:
    funding = f"${c['total_funding']:,.0f}" if c.get("total_funding") else "unknown"
    active  = ""
    if c.get("year_first") and c.get("year_last"):
        active = f" ({c['year_first']}–{c['year_last']})"
    revenue = c.get("revenue_estimate") or "unknown"
    emp     = f", ~{c['employee_count']} employees" if c.get("employee_count") else ""
    news    = c.get("recent_news") or "No recent news found."
    agency  = c.get("primary_agency") or "various agencies"

    return (
        f"**{c['firm']}** ({c.get('state', 'state unknown')})\n"
        f"  SBIR portfolio: {c['award_count']} awards, {c['phase_2_rate']}% Phase II rate, "
        f"{funding} total funding{active}. Primary agency: {agency}.\n"
        f"  Revenue: {revenue}{emp}. Web confidence: {c.get('web_confidence', 'low')}.\n"
        f"  Recent news: {news}"
    )


def _stream_synthesis(criteria: dict, top5: list[dict]) -> Iterator[str]:
    if not top5:
        yield "No suitable acquisition targets were found matching your criteria."
        return

    criteria_text  = _format_criteria(criteria)
    companies_text = "\n\n".join(_format_company_for_synthesis(c) for c in top5)

    system = (
        "You are a senior M&A analyst specializing in defense technology acquisitions. "
        "Analyze potential acquisition targets and provide specific, actionable strategic recommendations. "
        "Write for a corporate development audience — be direct, cite specific data, and focus on strategic fit. "
        "Use markdown formatting: ## headers for sections, **bold** for company names."
    )

    prompt = (
        f"## Acquirer Criteria\n{criteria_text}\n\n"
        f"## Candidate Companies\n{companies_text}\n\n"
        "Provide:\n"
        "1. A 2-3 paragraph landscape assessment covering: what technology themes emerge, "
        "what these companies signal about this market segment, and key strategic considerations.\n"
        "2. For each company (in a ## header for each), a targeted assessment covering: "
        "specific technology fit to the stated criteria, strategic rationale tied to stated goals, "
        "key risks or integration considerations, and why this company over alternatives.\n\n"
        "Be analytical and specific — reference actual award data, revenue signals, and agency relationships."
    )

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=SYNTHESIS_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for token in stream.text_stream:
            yield token


# ── Public streaming entry point ──────────────────────────────────────────────

def stream_acquisition_targets(criteria: dict) -> Iterator[str]:
    def ev(obj: dict) -> str:
        return f"data: {json.dumps(obj)}\n\n"

    yield ev({"type": "progress", "data": {"message": "Searching database for candidates…", "current": 0, "total": 0}})

    try:
        candidates = _find_candidates(criteria)
    except Exception as e:
        log.error("Candidate search error: %s", e)
        yield ev({"type": "progress", "data": {"message": f"Database search error: {e}", "current": 0, "total": 0}})
        yield ev({"type": "done"})
        return

    if not candidates:
        yield ev({"type": "progress", "data": {"message": "No candidates found. Try broadening your criteria.", "current": 0, "total": 0}})
        yield ev({"type": "done"})
        return

    research_pool = candidates[:MAX_RESEARCH]
    total = len(research_pool)
    yield ev({"type": "progress", "data": {
        "message": f"Found {len(candidates)} candidates — researching top {total}…",
        "current": 0, "total": total,
    }})

    # Parallel web research
    lock = threading.Lock()
    completed_count = [0]
    researched: list[dict] = []
    acquired:   list[dict] = []

    def research_one(company: dict) -> tuple[dict, str]:
        enriched = _research_company(company, criteria)
        with lock:
            completed_count[0] += 1
        return enriched, company["firm"]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_firm = {executor.submit(research_one, c): c["firm"] for c in research_pool}
        for future in as_completed(future_to_firm):
            try:
                enriched, firm = future.result()
            except Exception as e:
                log.warning("Research future error: %s", e)
                continue

            if enriched.get("already_acquired"):
                with lock:
                    acquired.append(enriched)
            else:
                with lock:
                    researched.append(enriched)

            yield ev({"type": "progress", "data": {
                "message": f"Researched {firm}…",
                "current": completed_count[0],
                "total": total,
            }})

    # Sort active companies by fit score, pick top 5
    top5 = sorted(researched, key=lambda x: x.get("fit_score", 0), reverse=True)[:TOP_N]
    acq_sorted = sorted(acquired, key=lambda x: x.get("fit_score", 0), reverse=True)

    yield ev({"type": "targets",  "data": top5})
    yield ev({"type": "acquired", "data": acq_sorted})

    # Stream Claude synthesis
    yield ev({"type": "progress", "data": {
        "message": "Generating strategic analysis…",
        "current": total, "total": total,
    }})

    try:
        for token in _stream_synthesis(criteria, top5):
            yield ev({"type": "text", "data": token})
    except Exception as e:
        log.error("Synthesis error: %s", e)
        yield ev({"type": "text", "data": f"\n\n[Analysis error: {e}]"})

    yield ev({"type": "done"})
