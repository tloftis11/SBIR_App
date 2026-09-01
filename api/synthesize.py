"""
Claude-powered synthesis: reason across semantic search results.

Retrieves 75 awards by similarity, computes aggregate statistics across the
full set, then passes both stats and representative abstracts to Claude so it
can answer open-ended questions analytically rather than just listing awards.

SSE event types:
  {"type": "text", "data": "chunk..."}   — Claude's streaming tokens
  {"type": "done"}                        — signals end of stream
"""

import json
import logging
import time
from collections import defaultdict
from typing import Iterator

import anthropic

from .models import AwardResult

log = logging.getLogger(__name__)

# ── Global stats cache ────────────────────────────────────────────────────────
# Fetched once from Supabase (no filters = full corpus), refreshed every hour.

_global_stats_cache: dict | None = None
_global_stats_ts: float = 0.0
_GLOBAL_TTL = 3600


def _get_global_stats() -> dict:
    global _global_stats_cache, _global_stats_ts
    if _global_stats_cache and time.time() - _global_stats_ts < _GLOBAL_TTL:
        return _global_stats_cache
    try:
        from .trends import get_trends
        from .models import SearchFilters
        _global_stats_cache = get_trends(SearchFilters())
        _global_stats_ts = time.time()
    except Exception as e:
        log.warning("Could not fetch global stats: %s", e)
        _global_stats_cache = _global_stats_cache or {}
    return _global_stats_cache


def _format_global_stats(data: dict) -> str:
    by_year    = data.get('by_year', [])
    by_agency  = data.get('by_agency', [])
    by_phase   = data.get('by_phase', [])
    top_states = data.get('top_states', [])

    total_awards  = sum(r.get('count', 0) for r in by_year)
    total_funding = sum(r.get('total_amount', 0) for r in by_year)
    year_min = by_year[0]['year']  if by_year else 1983
    year_max = by_year[-1]['year'] if by_year else 2026

    lines = [
        "DATABASE OVERVIEW (full corpus):",
        f"  Total awards: {total_awards:,}",
        f"  Total funding: ${total_funding:,}",
        f"  Year range: {year_min}–{year_max}",
    ]
    if by_agency[:8]:
        parts = [f"{r['agency']} ({r['count']:,} awards, ${r.get('total_amount', 0):,})"
                 for r in by_agency[:8]]
        lines.append(f"  Top agencies: {', '.join(parts)}")
    if by_phase:
        parts = [f"{r['phase']}: {r['count']:,}" for r in by_phase]
        lines.append(f"  By phase: {', '.join(parts)}")
    if top_states[:8]:
        parts = [f"{r['state']} ({r['count']:,})" for r in top_states[:8]]
        lines.append(f"  Top states: {', '.join(parts)}")

    return '\n'.join(lines)

CLAUDE_MODEL = "claude-opus-5"

SYSTEM = """\
You are an expert analyst of US SBIR/STTR federal innovation grant programs, with access to \
a curated database of 208,000+ awards spanning 1983–2026. You have been given a question \
and relevant database context — aggregate statistics plus representative award records \
retrieved by semantic search.

Answer the question directly and analytically. Reason across the full context: identify \
trends, compare agencies or time periods, highlight notable companies, and draw \
data-supported conclusions. Write in flowing prose. Do not produce bullet lists or \
enumerate individual awards. Cite specific dollar figures, companies, and patterns \
where they add clarity."""


def _compute_stats(results: list[AwardResult]) -> dict:
    by_agency: dict = defaultdict(lambda: {'count': 0, 'funding': 0})
    by_year:   dict = defaultdict(lambda: {'count': 0, 'funding': 0})
    by_phase:  dict = defaultdict(int)
    by_firm:   dict = defaultdict(lambda: {'count': 0, 'funding': 0})

    total_funding = 0
    funded = 0

    for a in results:
        amt = a.award_amount or 0
        if a.agency:
            by_agency[a.agency]['count'] += 1
            by_agency[a.agency]['funding'] += amt
        if a.award_year:
            by_year[a.award_year]['count'] += 1
            by_year[a.award_year]['funding'] += amt
        if a.phase:
            by_phase[a.phase] += 1
        if a.firm:
            by_firm[a.firm]['count'] += 1
            by_firm[a.firm]['funding'] += amt
        if amt:
            total_funding += amt
            funded += 1

    return {
        'n': len(results),
        'total_funding': total_funding,
        'avg_award': total_funding // funded if funded else 0,
        'by_agency': sorted(by_agency.items(), key=lambda x: x[1]['count'], reverse=True)[:8],
        'by_year': sorted(by_year.items())[-12:],
        'by_phase': dict(by_phase),
        'top_firms': sorted(by_firm.items(), key=lambda x: x[1]['count'], reverse=True)[:10],
    }


def _format_stats(stats: dict) -> str:
    lines = [
        f"AGGREGATE STATISTICS (across {stats['n']} semantically matched awards):",
        f"  Total funding represented: ${stats['total_funding']:,}",
    ]
    if stats['avg_award']:
        lines.append(f"  Average award size: ${stats['avg_award']:,}")

    if stats['by_agency']:
        parts = [
            f"{name} ({d['count']} awards, ${d['funding']:,})"
            for name, d in stats['by_agency']
        ]
        lines.append(f"  By agency: {', '.join(parts)}")

    if stats['by_phase']:
        parts = [f"{p}: {c}" for p, c in sorted(stats['by_phase'].items())]
        lines.append(f"  By phase: {', '.join(parts)}")

    if stats['by_year']:
        parts = [f"{yr}: {d['count']}" for yr, d in stats['by_year']]
        lines.append(f"  By year (recent): {', '.join(parts)}")

    if stats['top_firms']:
        parts = [f"{name} ({d['count']})" for name, d in stats['top_firms']]
        lines.append(f"  Top companies: {', '.join(parts)}")

    return '\n'.join(lines)


def _award_block(i: int, a: AwardResult) -> str:
    lines = [f"[{i}] {a.title or 'Untitled'}"]
    if a.firm:
        lines.append(f"Company: {a.firm}")
    meta = " | ".join(filter(None, [
        a.agency,
        a.phase,
        str(a.award_year) if a.award_year else None,
        f"${a.award_amount:,}" if a.award_amount else None,
        a.state_code,
    ]))
    if meta:
        lines.append(meta)
    if a.abstract:
        snippet = a.abstract[:500]
        if len(a.abstract) > 500:
            snippet += "..."
        lines.append(f"Abstract: {snippet}")
    return "\n".join(lines)


def stream_synthesis(question: str, results: list[AwardResult]) -> Iterator[str]:
    """
    Sync generator — yields SSE-formatted strings.
    FastAPI's StreamingResponse runs this in a thread pool.
    """
    if not results:
        yield f"data: {json.dumps({'type': 'text', 'data': 'No relevant awards found for that query.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Global corpus overview (cached, refreshed hourly)
    global_block = _format_global_stats(_get_global_stats())

    # Aggregate stats across ALL retrieved results
    stats = _compute_stats(results)
    stats_block = _format_stats(stats)

    # Include full abstracts only for the top 25 most similar
    top = results[:25]
    examples = "\n\n---\n\n".join(_award_block(i, a) for i, a in enumerate(top, 1))

    prompt = (
        f"Question: {question}\n\n"
        f"{global_block}\n\n"
        f"{stats_block}\n\n"
        f"REPRESENTATIVE AWARDS (top {len(top)} by relevance, for supporting detail):\n\n"
        f"{examples}\n\n"
        "Using the database overview, aggregate statistics, and representative awards above, "
        "answer the question comprehensively. Where useful, contextualise query-specific "
        "figures against the full corpus totals. Focus on patterns, trends, and insights "
        "rather than enumerating individual awards."
    )

    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'data': text})}\n\n"
    except Exception as e:
        log.error("Claude stream error: %s", e)
        yield f"data: {json.dumps({'type': 'text', 'data': f'[Analysis error: {e}]'})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
