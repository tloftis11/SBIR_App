"""
Semantic search: embed query with Voyage AI, retrieve via Supabase pgvector RPC.
"""

import time
import logging
from functools import lru_cache

import voyageai
from supabase import create_client, Client

from pipeline.config import (
    SUPABASE_URL, SUPABASE_SERVICE_KEY, VOYAGE_API_KEY, EMBED_MODEL
)
from .models import SearchFilters, AwardResult, FilterOptions

log = logging.getLogger(__name__)

_vo: voyageai.Client | None = None
_db: Client | None = None


def get_voyage() -> voyageai.Client:
    global _vo
    if _vo is None:
        _vo = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _vo


def get_db() -> Client:
    global _db
    if _db is None:
        _db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _db


def embed_query(text: str) -> list[float]:
    result = get_voyage().embed([text], model=EMBED_MODEL, input_type="query")
    return result.embeddings[0]


def semantic_search(query: str, filters: SearchFilters, limit: int) -> list[AwardResult]:
    embedding = embed_query(query)

    params = {
        "query_embedding": embedding,
        "match_count": limit,
        "filter_agency": filters.agency,
        "filter_phase": filters.phase,
        "filter_year_min": filters.year_min,
        "filter_year_max": filters.year_max,
        "filter_state": filters.state,
    }

    resp = get_db().rpc("match_awards", params).execute()
    return [AwardResult(**row) for row in (resp.data or [])]


# Cache filter options for 1 hour — they change only when new data is loaded.
_filter_cache: FilterOptions | None = None
_filter_cache_ts: float = 0.0
_FILTER_TTL = 3600


def get_filter_options() -> FilterOptions:
    global _filter_cache, _filter_cache_ts

    if _filter_cache and time.time() - _filter_cache_ts < _FILTER_TTL:
        return _filter_cache

    db = get_db()

    try:
        resp = db.rpc("get_filter_options").execute()
        data = resp.data
        _filter_cache = FilterOptions(
            agencies=data.get("agencies") or [],
            phases=data.get("phases") or [],
            states=data.get("states") or [],
            year_min=data.get("year_min"),
            year_max=data.get("year_max"),
        )
    except Exception:
        # Fallback if the RPC doesn't exist yet (run schema_api_functions.sql)
        log.warning("get_filter_options RPC not found — returning defaults")
        _filter_cache = FilterOptions(
            agencies=["Department of Defense", "Department of Health and Human Services",
                      "National Aeronautics and Space Administration",
                      "National Science Foundation", "Department of Energy",
                      "Department of Homeland Security", "Department of Agriculture",
                      "Department of Transportation", "Environmental Protection Agency",
                      "Department of Education", "Department of Commerce"],
            phases=["Phase I", "Phase II"],
            states=[],
            year_min=1983,
            year_max=2024,
        )

    _filter_cache_ts = time.time()
    return _filter_cache
