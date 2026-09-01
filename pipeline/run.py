"""
Main pipeline orchestrator.

Usage:
    # Full run (fetch → load → embed):
    python -m pipeline.run

    # Inspect API response before committing to a full run:
    python -m pipeline.fetch --dry-run

    # Re-embed only (awards already in DB, embeddings missing/stale):
    python -m pipeline.embed

    # Restrict to specific agencies:
    SBIR_AGENCIES=NASA,NSF python -m pipeline.run

Checkpointing:
    The pipeline is re-entrant. Interrupted runs can be restarted safely:
    - Awards are upserted (on_conflict=id), so duplicates are silently updated.
    - Embeddings skip awards that already have a row in award_embeddings.
"""

import logging
import time
import argparse
from tqdm import tqdm

from .config import SBIR_AGENCIES, SBIR_START_YEAR
from .fetch import fetch_all
from .transform import normalize
from .load import upsert_awards
from .embed import embed_and_store, fetch_unembedded_awards

log = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 250  # rows per Supabase upsert call


def run_ingest(agencies: list[str] | None = None, start_year: int | None = None) -> int:
    """
    Fetch awards from SBIR.gov and upsert into Supabase.

    Returns total rows written.
    """
    log.info("=== Phase 1: Fetch & Load ===")
    batch: list[dict] = []
    total_written = 0
    total_skipped = 0

    with tqdm(desc="Fetching awards", unit="award") as bar:
        for raw in fetch_all(agencies=agencies or SBIR_AGENCIES, start_year=start_year or SBIR_START_YEAR):
            record = normalize(raw)
            if record is None:
                total_skipped += 1
                continue

            batch.append(record)
            bar.update(1)

            if len(batch) >= UPSERT_BATCH_SIZE:
                total_written += upsert_awards(batch)
                batch = []

    # Flush remainder
    if batch:
        total_written += upsert_awards(batch)

    log.info("Ingest complete. Written=%d Skipped=%d", total_written, total_skipped)
    return total_written


def run_embed() -> int:
    """Embed all awards not yet in award_embeddings."""
    log.info("=== Phase 2: Embed ===")
    unembedded = fetch_unembedded_awards()
    log.info("Awards needing embeddings: %d", len(unembedded))

    if not unembedded:
        log.info("All awards already embedded.")
        return 0

    written = embed_and_store(unembedded)
    log.info("Embedding complete. Wrote %d embeddings.", written)
    return written


def main():
    parser = argparse.ArgumentParser(description="SBIR data pipeline")
    parser.add_argument(
        "--skip-ingest", action="store_true",
        help="Skip fetch/load phase (run embed only)"
    )
    parser.add_argument(
        "--skip-embed", action="store_true",
        help="Skip embed phase (run ingest only)"
    )
    parser.add_argument(
        "--agencies", nargs="+", metavar="AGENCY",
        help="Override SBIR_AGENCIES env var (e.g. --agencies NASA DOD NSF)"
    )
    parser.add_argument(
        "--start-year", type=int, metavar="YEAR",
        help="Only fetch awards from this year onwards"
    )
    args = parser.parse_args()

    t0 = time.time()

    if not args.skip_ingest:
        run_ingest(agencies=args.agencies, start_year=args.start_year)

    if not args.skip_embed:
        run_embed()

    elapsed = time.time() - t0
    log.info("Pipeline finished in %.1f minutes.", elapsed / 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
