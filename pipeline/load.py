"""
Supabase upsert helpers.

Uses the service-role key so it bypasses RLS during pipeline runs.
"""

import logging
from supabase import create_client, Client

from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY

log = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client


def upsert_awards(records: list[dict]) -> int:
    """
    Upsert a batch of normalised award dicts.

    Returns the number of rows written.
    """
    if not records:
        return 0
    # Deduplicate within the batch — PostgreSQL rejects ON CONFLICT DO UPDATE
    # when the same constrained key appears more than once in one statement.
    deduped = list({r["id"]: r for r in records}.values())
    db = get_client()
    db.table("awards").upsert(deduped, on_conflict="id").execute()
    log.debug("Upserted %d awards (%d dupes dropped)", len(deduped), len(records) - len(deduped))
    return len(deduped)


def get_embedded_ids() -> set[str]:
    """Return the set of award IDs that already have embeddings stored."""
    db = get_client()
    response = db.table("award_embeddings").select("award_id").execute()
    return {row["award_id"] for row in (response.data or [])}


def upsert_embeddings(rows: list[dict]) -> int:
    """
    Upsert embedding rows.

    Each row: {"award_id": str, "embedding": list[float], "model": str}
    Returns the number of rows written.
    """
    if not rows:
        return 0
    db = get_client()
    db.table("award_embeddings").upsert(rows, on_conflict="award_id").execute()
    log.debug("Upserted %d embeddings", len(rows))
    return len(rows)


def fetch_unembedded_awards(batch_size: int = 500) -> list[dict]:
    """
    Return awards that don't yet have a matching row in award_embeddings.

    Uses a NOT IN subquery via Supabase's filter syntax. For very large tables
    (200k+) you may prefer a LEFT JOIN query run directly in Postgres.
    """
    db = get_client()

    embedded_ids = get_embedded_ids()

    # Pull awards in pages and filter client-side for simplicity.
    # For large tables, replace with a Postgres RPC that does a server-side join.
    result = []
    page = 0
    page_size = 1000

    while True:
        resp = (
            db.table("awards")
            .select("id, title, abstract, keywords, agency, phase")
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break

        for row in rows:
            if row["id"] not in embedded_ids:
                result.append(row)

        if len(rows) < page_size:
            break
        page += 1

    return result
