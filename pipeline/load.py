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


def get_embedded_ids_for(award_ids: list[str]) -> set[str]:
    """Return which of the given award IDs already have embeddings."""
    if not award_ids:
        return set()
    db = get_client()
    resp = (
        db.table("award_embeddings")
        .select("award_id")
        .in_("award_id", award_ids)
        .execute()
    )
    return {row["award_id"] for row in (resp.data or [])}


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


def stream_awards(page_size: int = 500):
    """
    Generator: yield pages of award dicts using keyset pagination ordered by id.

    Keyset pagination avoids the statement-timeout that offset-based pagination
    hits on large tables (Supabase free tier has a 30-second limit).
    """
    db = get_client()
    cursor = ""  # empty string sorts before any real id

    while True:
        resp = (
            db.table("awards")
            .select("id, title, abstract, keywords, agency, phase")
            .gt("id", cursor)
            .order("id")
            .limit(page_size)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        yield rows
        if len(rows) < page_size:
            break
        cursor = rows[-1]["id"]
