"""
Paginated fetcher for the SBIR.gov public API.

Dry-run usage:
    python -m pipeline.fetch --dry-run

This prints the raw first page so you can verify field names before a full load.
The API returns roughly 180 000 awards total; expect ~10–15 min for a full pull
at SBIR_PAGE_SIZE=250 with the default rate-limiting delay.
"""

import time
import json
import logging
import argparse
from typing import Iterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import SBIR_API_BASE, SBIR_PAGE_SIZE, SBIR_REQUEST_DELAY, SBIR_AGENCIES, SBIR_START_YEAR

log = logging.getLogger(__name__)


def _parse_results(data: dict) -> list[dict]:
    """Handle the two common response shapes from the SBIR API."""
    # Shape 1: {"data": [...], "totalCount": N}
    if "data" in data and isinstance(data["data"], list):
        return data["data"]
    # Shape 2: Solr-style {"response": {"docs": [...], "numFound": N}}
    if "response" in data and "docs" in data["response"]:
        return data["response"]["docs"]
    # Shape 3: flat list at top level
    if isinstance(data, list):
        return data
    return []


def _parse_total(data: dict) -> int:
    if "totalCount" in data:
        return int(data["totalCount"])
    if "response" in data and "numFound" in data["response"]:
        return int(data["response"]["numFound"])
    return 0


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def _get_page(client: httpx.Client, params: dict) -> dict:
    resp = client.get(f"{SBIR_API_BASE}/awards", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_awards(
    agency: str | None = None,
    year: int | None = None,
    phase: str | None = None,
) -> Iterator[dict]:
    """
    Yield every award matching the given filters.

    Paginates automatically; respects SBIR_REQUEST_DELAY between pages.
    Each yielded item is a raw dict from the API — transform.py normalises it.
    """
    params: dict = {"rows": SBIR_PAGE_SIZE, "start": 0}
    if agency:
        params["agency"] = agency
    if year:
        params["year"] = year
    if phase:
        params["phase"] = phase

    with httpx.Client(headers={"Accept": "application/json"}) as client:
        page = 0
        total_seen = 0

        while True:
            params["start"] = page * SBIR_PAGE_SIZE
            log.debug("Fetching page %d (start=%d)", page, params["start"])

            data = _get_page(client, params)
            records = _parse_results(data)

            if not records:
                break

            yield from records
            total_seen += len(records)
            log.info("Fetched %d records so far (page %d)", total_seen, page)

            if len(records) < SBIR_PAGE_SIZE:
                break  # last page

            page += 1
            time.sleep(SBIR_REQUEST_DELAY)


def fetch_all(agencies: list[str] | None = None, start_year: int | None = None) -> Iterator[dict]:
    """
    Yield awards for all configured agencies (or every agency if unconfigured).

    Iterates agency by agency so a partial failure only loses one slice.
    """
    target_agencies = agencies or SBIR_AGENCIES or [None]  # None = all agencies

    for agency in target_agencies:
        log.info("Fetching agency=%s start_year=%s", agency or "ALL", start_year)
        yield from fetch_awards(agency=agency, year=start_year)


# ---------------------------------------------------------------------------
# CLI dry-run helper
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch one page and print raw JSON, then exit")
    args = parser.parse_args()

    if args.dry_run:
        import httpx as _httpx
        with _httpx.Client() as c:
            resp = c.get(f"{SBIR_API_BASE}/awards", params={"rows": 3, "start": 0}, timeout=15)
            print(json.dumps(resp.json(), indent=2))
    else:
        for i, award in enumerate(fetch_all()):
            print(award.get("firm", ""), award.get("title", "")[:60])
            if i >= 9:
                print("... (pass --dry-run for a smaller sample)")
                break
