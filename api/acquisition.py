"""
Acquisition info: check whether an SBIR company has been acquired.

Flow per company:
  1. Check company_acquisition_info table (cache for 6 months)
  2. If stale/missing, run a Claude web search with company context
  3. Parse JSON from Claude's response and store back to cache
  4. Return the result
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone

import anthropic

from .search import get_db

log = logging.getLogger(__name__)

CACHE_TTL_DAYS = 180
CLAUDE_MODEL   = "claude-opus-5"


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _get_cached(firm: str) -> dict | None:
    try:
        resp = get_db().table("company_acquisition_info").select("*").eq("firm", firm).execute()
        if not resp.data:
            return None
        row = resp.data[0]
        checked_at = datetime.fromisoformat(row["checked_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - checked_at).days > CACHE_TTL_DAYS:
            return None
        return row
    except Exception as e:
        log.warning("Acquisition cache read error: %s", e)
        return None


def _store(firm: str, result: dict):
    try:
        get_db().table("company_acquisition_info").upsert({
            "firm":             firm,
            "acquired":         result.get("acquired", False),
            "acquired_by":      result.get("acquired_by"),
            "acquisition_year": result.get("acquisition_year"),
            "confidence":       result.get("confidence", "low"),
            "notes":            result.get("notes"),
            "checked_at":       datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        log.warning("Acquisition cache write error: %s", e)


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    """Find the first balanced {...} block and parse it as JSON."""
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


# ── Claude web search ─────────────────────────────────────────────────────────

def _search_web(firm: str, state: str | None, primary_agency: str | None) -> dict:
    context = ""
    if primary_agency:
        context += f" that received federal SBIR/STTR grants from {primary_agency}"
    if state:
        context += f", based in {state}"

    prompt = (
        f'Search for acquisition information about "{firm}", '
        f"a US technology/defense company{context}.\n\n"
        "Determine whether this specific company has ever been acquired by another company. "
        "Be careful to distinguish it from similarly-named firms — use the state and agency "
        "context to confirm you have the right company.\n\n"
        "After searching, respond with ONLY a valid JSON object — no other text:\n"
        "{\n"
        '  "acquired": true or false,\n'
        '  "acquired_by": "Acquiring Company Name" or null,\n'
        '  "acquisition_year": year as integer or null,\n'
        '  "confidence": "high", "medium", or "low",\n'
        '  "notes": "one sentence summary of what you found"\n'
        "}\n\n"
        "If you find no credible evidence of an acquisition, set acquired to false. "
        "Set confidence to low if results were ambiguous or the company is obscure."
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
        messages=[{"role": "user", "content": prompt}],
    )

    text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    parsed = _extract_json(text)
    if parsed:
        return parsed

    log.warning("Could not parse acquisition JSON for %s — raw: %s", firm, text[:200])
    return {
        "acquired":         False,
        "acquired_by":      None,
        "acquisition_year": None,
        "confidence":       "low",
        "notes":            "No acquisition information found.",
    }


# ── Public entry point ────────────────────────────────────────────────────────

def get_acquisition_info(firm: str, awards: list[dict]) -> dict:
    """
    Return acquisition info for a company, using the cache when fresh.
    Falls back to a Claude web search if the cache is stale or empty.
    """
    cached = _get_cached(firm)
    if cached:
        return {**cached, "from_cache": True}

    # Derive search context from the company's award history
    states   = [a.get("state_code") for a in awards if a.get("state_code")]
    agencies = [a.get("agency")     for a in awards if a.get("agency")]
    state          = Counter(states).most_common(1)[0][0]   if states   else None
    primary_agency = Counter(agencies).most_common(1)[0][0] if agencies else None

    try:
        result = _search_web(firm, state, primary_agency)
    except Exception as e:
        log.error("Acquisition search failed for %s: %s", firm, e)
        result = {
            "acquired":         False,
            "acquired_by":      None,
            "acquisition_year": None,
            "confidence":       "low",
            "notes":            f"Search error: {e}",
        }

    _store(firm, result)
    return {**result, "from_cache": False}
