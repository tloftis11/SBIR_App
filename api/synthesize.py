"""
Claude-powered synthesis: stream an analysis of semantic search results.

Each SSE event is JSON-encoded so newlines in the text are safe to transmit.
Event types:
  {"type": "results", "data": [...awards...]}   — first event, the matched awards
  {"type": "text",    "data": "chunk..."}        — Claude's streaming tokens
  {"type": "done"}                               — signals end of stream
"""

import json
import logging
from typing import Iterator

import anthropic

from .models import AwardResult

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-opus-5"

SYSTEM = """\
You are an expert analyst of SBIR/STTR federal innovation grants. Given a set of award \
records, provide a focused, insightful synthesis: identify the core technology themes, \
highlight notable companies and research institutions, note funding trends (agencies, \
phases, dollar amounts, years), and answer the user's specific question directly. \
Be concrete — cite specific companies and awards from the data by name. \
Write in flowing prose, not bullet lists."""


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
        snippet = a.abstract[:600]
        if len(a.abstract) > 600:
            snippet += "..."
        lines.append(f"Abstract: {snippet}")
    return "\n".join(lines)


def stream_synthesis(question: str, results: list[AwardResult]) -> Iterator[str]:
    """
    Sync generator — yields SSE-formatted strings.
    FastAPI's StreamingResponse runs this in a thread pool.
    """
    # First event: the matched awards so the frontend can render them immediately
    awards_payload = [r.model_dump() for r in results]
    yield f"data: {json.dumps({'type': 'results', 'data': awards_payload})}\n\n"

    if not results:
        yield f"data: {json.dumps({'type': 'text', 'data': 'No matching awards found for that query.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    context = "\n\n---\n\n".join(_award_block(i, a) for i, a in enumerate(results, 1))
    prompt = (
        f'The user asked: "{question}"\n\n'
        f"I retrieved the {len(results)} most semantically relevant SBIR/STTR awards:\n\n"
        f"{context}\n\n"
        "Please analyze these awards and answer the user's question directly. "
        "Identify key technology themes, notable companies, and relevant funding patterns."
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
