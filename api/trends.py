"""
Trend aggregation endpoints: awards by year, agency, phase, state.
"""

import json
import logging
from typing import Iterator

import anthropic
from supabase import Client

from .search import get_db
from .models import SearchFilters

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-5"

TREND_SYSTEM = """\
You are an expert analyst of US federal SBIR/STTR innovation grant programs. \
Answer the user's question about trends, funding patterns, and agency behavior \
using your knowledge of the program and any context provided. \
Be specific, cite numbers when you know them, and write in flowing prose."""


def _build_filters(db: Client, filters: SearchFilters):
    q = db.table("awards").select(
        "award_year, agency, phase, state_code, award_amount",
        count="exact"
    )
    if filters.agency:
        q = q.eq("agency", filters.agency)
    if filters.phase:
        q = q.eq("phase", filters.phase)
    if filters.year_min:
        q = q.gte("award_year", filters.year_min)
    if filters.year_max:
        q = q.lte("award_year", filters.year_max)
    if filters.state:
        q = q.eq("state_code", filters.state)
    return q


def get_trends(filters: SearchFilters) -> dict:
    db = get_db()

    # --- By year ---
    resp = (
        db.rpc("trends_by_year", {
            "filter_agency": filters.agency,
            "filter_phase": filters.phase,
            "filter_year_min": filters.year_min,
            "filter_year_max": filters.year_max,
            "filter_state": filters.state,
        }).execute()
    )
    by_year = resp.data or []

    # --- By agency ---
    resp = (
        db.rpc("trends_by_agency", {
            "filter_phase": filters.phase,
            "filter_year_min": filters.year_min,
            "filter_year_max": filters.year_max,
            "filter_state": filters.state,
        }).execute()
    )
    by_agency = resp.data or []

    # --- By phase ---
    resp = (
        db.rpc("trends_by_phase", {
            "filter_agency": filters.agency,
            "filter_year_min": filters.year_min,
            "filter_year_max": filters.year_max,
            "filter_state": filters.state,
        }).execute()
    )
    by_phase = resp.data or []

    # --- Top states ---
    resp = (
        db.rpc("trends_top_states", {
            "filter_agency": filters.agency,
            "filter_phase": filters.phase,
            "filter_year_min": filters.year_min,
            "filter_year_max": filters.year_max,
        }).execute()
    )
    top_states = resp.data or []

    return {
        "by_year": by_year,
        "by_agency": by_agency,
        "by_phase": by_phase,
        "top_states": top_states,
    }


def stream_trend_analysis(question: str) -> Iterator[str]:
    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=TREND_SYSTEM,
            messages=[{"role": "user", "content": question}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'data': text})}\n\n"
    except Exception as e:
        log.error("Claude trend stream error: %s", e)
        yield f"data: {json.dumps({'type': 'text', 'data': f'[Error: {e}]'})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
