"""
Company search, portfolio, and Claude synthesis endpoints.
"""

import json
import logging
from typing import Iterator

import anthropic

from .search import get_db

log = logging.getLogger(__name__)
CLAUDE_MODEL = "claude-opus-5"

COMPANY_SYSTEM = """\
You are an expert analyst of US federal SBIR/STTR innovation funding. \
Given a company's award portfolio, provide a sharp, specific synthesis: \
what technologies they specialize in, which agencies fund them and why, \
how their research has evolved over time, and what their portfolio signals \
about their competitive position and capabilities. Be concrete — cite \
specific award titles and amounts. Write in flowing prose."""


def search_companies(
    query: str = "",
    sort_by: str = "count",
    filter_agency: str | None = None,
    filter_state: str | None = None,
    filter_phase: str | None = None,
    filter_year_min: int | None = None,
    filter_year_max: int | None = None,
    limit: int = 30,
) -> list[dict]:
    resp = get_db().rpc("search_companies", {
        "query": query,
        "sort_by": sort_by,
        "filter_agency": filter_agency,
        "filter_state": filter_state,
        "filter_phase": filter_phase,
        "filter_year_min": filter_year_min,
        "filter_year_max": filter_year_max,
        "result_limit": limit,
    }).execute()
    return resp.data or []


def get_company_awards(firm: str) -> list[dict]:
    resp = get_db().rpc("company_awards", {"firm_name": firm}).execute()
    return resp.data or []


def stream_company_analysis(firm: str, awards: list[dict], question: str) -> Iterator[str]:
    if not awards:
        yield f"data: {json.dumps({'type': 'text', 'data': 'No awards found for this company.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Build context from awards
    lines = []
    for a in awards[:40]:  # cap context
        meta = " | ".join(filter(None, [
            a.get("agency"), a.get("phase"),
            str(a["award_year"]) if a.get("award_year") else None,
            f"${a['award_amount']:,}" if a.get("award_amount") else None,
        ]))
        lines.append(f"- {a.get('title', 'Untitled')} [{meta}]")
        if a.get("abstract"):
            lines.append(f"  {a['abstract'][:300]}")

    context = "\n".join(lines)
    total = len(awards)
    shown = min(40, total)

    prompt = (
        f'Company: {firm}\n'
        f'Total SBIR/STTR awards: {total} (showing {shown} below)\n\n'
        f'{context}\n\n'
        f'User question: {question}'
    )

    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=COMPANY_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'data': text})}\n\n"
    except Exception as e:
        log.error("Claude company stream error: %s", e)
        yield f"data: {json.dumps({'type': 'text', 'data': f'[Error: {e}]'})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"
